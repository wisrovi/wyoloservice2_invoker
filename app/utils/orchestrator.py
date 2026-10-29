# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Hybrid Execution Orchestrator for Worker Invoker.

Supports dual orchestration modes:
- Docker mode: Spawns ephemeral containers via the local Docker daemon.
- Kubernetes mode: Spawns ephemeral Pods directly on the local node using the in-cluster K8s API.
"""

import json
import os
import re
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import requests


def is_k8s_environment() -> bool:
    """Detect if running inside a Kubernetes cluster."""
    orch = os.getenv("ORCHESTRATOR", "").strip().lower()
    if orch in ("k8s", "kubernetes"):
        return True
    if orch == "docker":
        return False
    token_file = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    return bool(os.getenv("KUBERNETES_SERVICE_HOST")) and os.path.exists(token_file)


def sanitize_k8s_name(name: str) -> str:
    """Sanitize container/trial name into a valid Kubernetes DNS-1123 label."""
    sanitized = re.sub(r"[^a-z0-9\-]", "-", name.lower()).strip("-")
    sanitized = re.sub(r"-+", "-", sanitized)
    if not sanitized:
        sanitized = "wyolo-task"
    return sanitized[:63]


def get_optimal_gpu_device(preferred_gpu: Optional[str] = None) -> List[str]:
    """Determine the optimal target GPU device ID(s) for task execution.

    If preferred_gpu is provided (e.g. '1', '0,1', or 'all'), uses that specification.
    Otherwise, queries nvidia-smi to automatically pick the GPU with the highest
    free VRAM to prevent Out-Of-Memory (OOM) collisions. Defaults to ['0'] on failure.

    Args:
        preferred_gpu: Optional override specifying preferred GPU index or 'all'.

    Returns:
        List[str]: List of GPU device index strings, or ['all'].
    """
    if preferred_gpu:
        pref = str(preferred_gpu).strip()
        if pref.lower() in ("all", "-1"):
            return ["all"]
        return [g.strip() for g in pref.split(",") if g.strip()]

    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,memory.free", "--format=csv,noheader,nounits"],
            text=True,
            timeout=3,
        ).strip()
        gpus: List[Tuple[str, float]] = []
        for line in out.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                try:
                    gpus.append((parts[0], float(parts[1])))
                except ValueError:
                    pass
        if gpus:
            gpus.sort(key=lambda x: x[1], reverse=True)
            return [gpus[0][0]]
    except Exception:
        pass
    return ["0"]


def get_gpu_utilization(target_gpu: str = "0") -> float:
    """Retrieve actual GPU compute utilization percentage via nvidia-smi.

    Args:
        target_gpu: Target GPU index (or 'all').

    Returns:
        float: GPU utilization percentage between 0.0 and 100.0.
    """
    try:
        gpu_id = "0" if target_gpu == "all" else target_gpu
        out = subprocess.check_output(
            ["nvidia-smi", f"--id={gpu_id}", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            text=True,
            timeout=2,
        ).strip()
        if out:
            return float(out.splitlines()[0])
    except Exception:
        pass
    return 0.0


class BaseOrchestrator:
    """Abstract interface for task orchestration."""

    def run_eda(
        self,
        image_name: str,
        name: str,
        environments: Dict[str, str],
        volumes: Dict[str, Any],
        command: List[str],
    ) -> str:
        """Run temporary EDA container/pod and return stdout string."""
        raise NotImplementedError

    def start_executor(
        self,
        image_name: str,
        executor_name: str,
        environments: Dict[str, str],
        volumes: Dict[str, Any],
        command_str: str,
        shm_size_bytes: int,
        mem_limit: int,
        cpu_limit: float,
        results_dir: str,
        timeout_seconds: int,
        invoker_name: str,
        redis_client: Any,
    ) -> int:
        """Run training executor container/pod and return exit code."""
        raise NotImplementedError

    def clean_orphaned_tasks(self) -> int:
        """Sweep and remove lingering executor and eda containers or pods."""
        raise NotImplementedError


class DockerOrchestrator(BaseOrchestrator):
    """Orchestrates tasks via the local Docker daemon."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize DockerOrchestrator with configuration."""
        self.config = config or {}
        import docker  # type: ignore

        self.client = docker.from_env()

    def run_eda(
        self,
        image_name: str,
        name: str,
        environments: Dict[str, str],
        volumes: Dict[str, Any],
        command: List[str],
    ) -> str:
        """Run temporary EDA container using local Docker daemon."""
        try:
            existing = self.client.containers.get(name)
            existing.remove(force=True)
        except Exception:
            pass

        print(f"[EDA][Docker] Spawning temp container {name} with image {image_name}...")
        container_output = self.client.containers.run(
            image=image_name,
            name=name,
            detach=False,
            privileged=True,
            network_mode="host",
            environment=environments,
            volumes=volumes,
            command=command,
            remove=True,
        )
        return container_output.decode("utf-8", errors="ignore")

    def clean_orphaned_tasks(self) -> int:
        """Sweep and remove lingering wyolo executor and eda containers."""
        cleaned = 0
        try:
            containers = self.client.containers.list(all=True)
            for c in containers:
                c_name = getattr(c, "name", "")
                if c_name and (c_name.startswith("wyolo_executor_") or c_name.startswith("wyolo_eda_runner_")):
                    print(
                        f"🧹 [ORPHAN SWEEPER][Docker] Removing stale/orphaned container: {c_name} (Status: {getattr(c, 'status', 'unknown')})",
                        flush=True,
                    )
                    try:
                        c.remove(force=True)
                        cleaned += 1
                    except Exception as e:
                        print(f"⚠️ [ORPHAN SWEEPER] Failed to remove {c_name}: {e}")
        except Exception as exc:
            print(f"⚠️ [ORPHAN SWEEPER] Error listing docker containers: {exc}")
        return cleaned

    def start_executor(
        self,
        image_name: str,
        executor_name: str,
        environments: Dict[str, str],
        volumes: Dict[str, Any],
        command_str: str,
        shm_size_bytes: int,
        mem_limit: int,
        cpu_limit: float,
        results_dir: str,
        timeout_seconds: int,
        invoker_name: str,
        redis_client: Any,
    ) -> int:
        """Start the training executor container and stream logs."""
        import docker  # type: ignore

        try:
            existing = self.client.containers.get(executor_name)
            print(f"--- [INVOKER][Docker] Found existing container {executor_name}. Removing... ---")
            existing.remove(force=True)
        except Exception:
            pass

        target_gpu_pref = (
            environments.get("GPU_DEVICE_ID")
            or environments.get("CUDA_VISIBLE_DEVICES")
            or (self.config.get("gpu_device_id") if isinstance(self.config, dict) else None)
        )
        selected_gpus = get_optimal_gpu_device(target_gpu_pref)

        if "all" in selected_gpus:
            dev_requests = [docker.types.DeviceRequest(count=-1, capabilities=[["gpu"]])]
            environments["CUDA_VISIBLE_DEVICES"] = "all"
        else:
            dev_requests = [docker.types.DeviceRequest(device_ids=selected_gpus, capabilities=[["gpu"]])]
            gpu_str = ",".join(selected_gpus)
            environments["CUDA_VISIBLE_DEVICES"] = gpu_str
            environments["NVIDIA_VISIBLE_DEVICES"] = gpu_str

        # Defensive thread limits to prevent multi-threading CPU freeze
        cpu_val = max(1, int(cpu_limit)) if cpu_limit > 0 else 2
        max_threads = str(min(4, max(1, cpu_val)))
        thread_vars = {
            "OMP_NUM_THREADS": max_threads,
            "MKL_NUM_THREADS": max_threads,
            "OPENBLAS_NUM_THREADS": max_threads,
            "VECLIB_MAXIMUM_THREADS": max_threads,
            "NUMEXPR_NUM_THREADS": max_threads,
            "TORCH_NUM_THREADS": max_threads,
        }
        for var_name, var_val in thread_vars.items():
            if var_name not in environments:
                environments[var_name] = var_val

        run_kwargs = {
            "image": image_name,
            "name": executor_name,
            "hostname": environments.get("USER", "default_user"),
            "detach": True,
            "remove": False,
            "privileged": True,
            "network_mode": "host",
            "shm_size": shm_size_bytes,
            "tty": False,
            "nano_cpus": int(cpu_limit * 1e9),
            "mem_limit": mem_limit,
            "cap_add": ["SYS_ADMIN", "DAC_READ_SEARCH", "NET_ADMIN", "SYS_RESOURCE"],
            "device_requests": dev_requests,
            "environment": environments,
            "labels": {
                "autoheal": "true",
                "com.centurylinklabs.watchtower.enable": "true",
            },
            "volumes": volumes,
            "command": command_str,
        }
        if mem_limit > 0:
            run_kwargs["memswap_limit"] = mem_limit

        container = self.client.containers.run(**run_kwargs)

        print(f"--- [INVOKER][Docker] Executor {executor_name} started. Streaming logs... ---", flush=True)

        stop_monitor = False
        user_cancelled = False
        log_file_path = os.path.join(results_dir, f"logs_{executor_name}.txt")

        task_id = environments.get("TASK_ID") or environments.get("CELERY_TASK_ID")
        study_id = environments.get("STUDY_ID")

        def check_docker_cancellation() -> bool:
            """Check Redis for cancellation requests targeting this task, study, or host node drain."""
            if not redis_client:
                return False
            try:
                keys = []
                if task_id:
                    keys.extend([f"wyolo:task:{task_id}:cancel", f"task:{task_id}:cancel"])
                if study_id:
                    keys.extend(
                        [f"study:{study_id}:cancel", f"wyolo:study:{study_id}:cancel", f"study:{study_id}:cancelled"]
                    )
                # Check host node-level drain or eviction
                worker_ip = environments.get("WORKER_HOST") or os.getenv("WORKER_HOST")
                if worker_ip:
                    keys.append(f"invoker:{worker_ip}:cancel_active")
                    drain_val = redis_client.get(f"invoker:{worker_ip}:drain")
                    if drain_val:
                        try:
                            drain_data = json.loads(drain_val.decode() if isinstance(drain_val, bytes) else drain_val)
                            if drain_data.get("draining") and drain_data.get("evict", True):
                                return True
                        except Exception:
                            pass
                for k in keys:
                    if redis_client.get(k):
                        return True
            except Exception:
                pass
            return False

        def get_current_epoch() -> str:
            """Extract current epoch from container logs."""
            try:
                logs = container.logs(tail=100).decode("utf-8", errors="ignore")
                matches = re.findall(r"\s+(\d+)/\d+\s+\d+\.\d+G", logs)
                if matches:
                    return matches[-1]
            except Exception:
                pass
            return "N/A"

        def monitor_resources():
            """Monitor container resource usage, check for cancellation, and write telemetry."""
            nonlocal user_cancelled
            while not stop_monitor:
                try:
                    if check_docker_cancellation():
                        user_cancelled = True
                        print(
                            f"⚠️ [INVOKER][Docker] Cancellation signal detected for task {task_id}! "
                            f"Killing container {executor_name}...",
                            flush=True,
                        )
                        try:
                            container.kill()
                        except Exception:
                            try:
                                container.stop(timeout=5)
                            except Exception:
                                pass
                        break

                    container.reload()
                    stats = container.stats(stream=False)
                    cpu_stats = stats.get("cpu_stats", {})
                    precpu_stats = stats.get("precpu_stats", {})
                    cpu_delta = cpu_stats.get("cpu_usage", {}).get("total_usage", 0) - precpu_stats.get(
                        "cpu_usage", {}
                    ).get("total_usage", 0)
                    system_delta = cpu_stats.get("system_cpu_usage", 0) - precpu_stats.get("system_cpu_usage", 0)
                    online_cpus = cpu_stats.get("online_cpus", 1) or 1
                    cpu_percent = (
                        (cpu_delta / system_delta) * online_cpus * 100.0 if system_delta > 0 and cpu_delta > 0 else 0.0
                    )
                    memory_usage = stats.get("memory_stats", {}).get("usage", 0)
                    ram_mb = memory_usage / (1024 * 1024) if memory_usage else 0.0

                    primary_gpu = selected_gpus[0] if selected_gpus and selected_gpus[0] != "all" else "0"
                    real_gpu_pct = get_gpu_utilization(primary_gpu)

                    stats_payload = {
                        "status": "cancelled" if user_cancelled else "running",
                        "cpu": round(cpu_percent, 2),
                        "ram_mb": round(ram_mb, 2),
                        "gpu": real_gpu_pct,
                        "epoch": get_current_epoch(),
                        "timestamp": time.time(),
                    }
                    if redis_client:
                        redis_client.set(
                            f"executor:{executor_name}:stats",
                            json.dumps(stats_payload),
                            ex=30,
                        )
                    if results_dir:
                        telemetry_file = os.path.join(results_dir, f"telemetry_{executor_name}.json")
                        tmp_file = telemetry_file + ".tmp"
                        try:
                            with open(tmp_file, "w", encoding="utf-8") as f:
                                json.dump(stats_payload, f, indent=4)
                            os.replace(tmp_file, telemetry_file)
                        except Exception:
                            pass
                except Exception:
                    pass
                time.sleep(2)

        monitor_thread = threading.Thread(target=monitor_resources, daemon=True)
        monitor_thread.start()

        def stream_logs():
            """Stream container stdout and stderr to logs and console."""
            try:
                with open(log_file_path, "w", encoding="utf-8") as log_file:
                    for line in container.logs(stream=True, follow=True):
                        try:
                            decoded = line.decode("utf-8", errors="replace").rstrip()
                            if decoded:
                                print(f"[{executor_name}] {decoded}", flush=True)
                                log_file.write(decoded + "\n")
                                log_file.flush()
                        except Exception:
                            pass
            except Exception as exc:
                print(f"--- [INVOKER][Docker] Error streaming logs: {exc} ---")

        log_thread = threading.Thread(target=stream_logs, daemon=True)
        log_thread.start()

        try:
            result = container.wait(timeout=timeout_seconds)
            exit_code = result.get("StatusCode", 0)
        except Exception as exc:
            container.stop(timeout=30)
            container.remove(force=True)
            raise RuntimeError(f"Executor failed or timed out: {exc}")
        finally:
            stop_monitor = True
            monitor_thread.join(timeout=2)
            log_thread.join(timeout=5)

        if user_cancelled:
            try:
                container.stop(timeout=10)
                container.remove(force=True)
            except Exception:
                pass
            raise RuntimeError(f"Executor {executor_name} was cancelled by user/operator request.")

        if exit_code != 0 and results_dir:
            try:
                tail_logs = container.logs(tail=200).decode("utf-8", errors="replace")
                if tail_logs:
                    with open(log_file_path, "a", encoding="utf-8") as log_file:
                        log_file.write(f"\n--- [Docker Container Final Failure Logs (ExitCode: {exit_code})] ---\n")
                        log_file.write(tail_logs)
                        log_file.flush()
            except Exception as log_err:
                print(f"--- [INVOKER][Docker] Could not capture final logs: {log_err} ---")

        if results_dir:
            telemetry_file = os.path.join(results_dir, f"telemetry_{executor_name}.json")
            try:
                with open(telemetry_file, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "status": "finished",
                            "cpu": 0,
                            "ram_mb": 0,
                            "gpu": 0.0,
                            "timestamp": time.time(),
                        },
                        f,
                        indent=4,
                    )
            except Exception:
                pass

        return exit_code


class KubernetesOrchestrator(BaseOrchestrator):
    """Orchestrates tasks directly as Kubernetes Pods using in-cluster API."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize KubernetesOrchestrator with cluster credentials."""
        self.config = config or {}
        token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        if os.path.exists(token_path):
            with open(token_path, "r", encoding="utf-8") as f:
                self.token = f.read().strip()
        else:
            self.token = os.getenv("K8S_TOKEN", "")

        self.ca_cert = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        if not os.path.exists(self.ca_cert):
            self.ca_cert = False  # type: ignore

        host = os.getenv("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
        port = os.getenv("KUBERNETES_SERVICE_PORT", "443")
        self.base_url = f"https://{host}:{port}"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        ns_file = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
        if os.path.exists(ns_file):
            with open(ns_file, "r", encoding="utf-8") as f:
                self.namespace = f.read().strip()
        else:
            self.namespace = os.getenv("K8S_NAMESPACE", "train-service")

        self.node_name = os.getenv("WORKER_HOSTNAME") or os.getenv("K8S_NODE_NAME") or ""

    def _delete_pod_if_exists(self, pod_name: str) -> None:
        """Safely delete any pre-existing pod with the same name."""
        try:
            url = f"{self.base_url}/api/v1/namespaces/{self.namespace}/pods/{pod_name}?gracePeriodSeconds=0"
            resp = requests.delete(url, headers=self.headers, verify=self.ca_cert, timeout=10)
            if resp.status_code in (200, 202):
                # Wait briefly until the pod is deleted
                for _ in range(10):
                    time.sleep(1)
                    check = requests.get(
                        f"{self.base_url}/api/v1/namespaces/{self.namespace}/pods/{pod_name}",
                        headers=self.headers,
                        verify=self.ca_cert,
                        timeout=5,
                    )
                    if check.status_code == 404:
                        break
        except Exception:
            pass

    def clean_orphaned_tasks(self) -> int:
        """Sweep and remove lingering wyolo executor and eda pods on this node."""
        cleaned = 0
        try:
            query_url = (
                f"{self.base_url}/api/v1/namespaces/{self.namespace}/pods"
                "?labelSelector=app in (wyolo-executor,wyolo-eda)"
            )
            resp = requests.get(query_url, headers=self.headers, verify=self.ca_cert, timeout=10)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for pod in items:
                    pod_node = pod.get("spec", {}).get("nodeName", "")
                    pod_name = pod.get("metadata", {}).get("name", "")
                    if not self.node_name or pod_node == self.node_name:
                        print(
                            f"🧹 [ORPHAN SWEEPER][K8s] Deleting orphaned pod: {pod_name} on node {pod_node}",
                            flush=True,
                        )
                        self._delete_pod_if_exists(pod_name)
                        cleaned += 1
        except Exception as exc:
            print(f"⚠️ [ORPHAN SWEEPER] Error listing K8s pods: {exc}")
        return cleaned

    def run_eda(
        self,
        image_name: str,
        name: str,
        environments: Dict[str, str],
        volumes: Dict[str, Any],
        command: List[str],
    ) -> str:
        """Run temporary EDA Pod using in-cluster Kubernetes API."""
        import uuid

        eda_uid = uuid.uuid4().hex[:6]
        base_name = f"{name}-{self.node_name}" if self.node_name and self.node_name not in name else name
        pod_name = sanitize_k8s_name(f"{base_name}-{eda_uid}")
        self._delete_pod_if_exists(pod_name)

        command_str = " ".join(command) if isinstance(command, list) else str(command)

        if environments.get("NVIDIA_VISIBLE_DEVICES") in ("void", None, ""):
            environments["NVIDIA_VISIBLE_DEVICES"] = "0"
        environments["NVIDIA_DRIVER_CAPABILITIES"] = "all"

        print(f"[EDA][K8s] Spawning temp Pod {pod_name} on node {self.node_name} with image {image_name}...")

        pod_manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": pod_name,
                "namespace": self.namespace,
                "labels": {
                    "app": "wyolo-eda",
                    "node": self.node_name,
                },
            },
            "spec": {
                "nodeName": self.node_name,
                "restartPolicy": "Never",
                "tolerations": [
                    {"key": "nvidia.com/gpu", "operator": "Exists", "effect": "NoSchedule"},
                    {"key": "node.kubernetes.io/disk-pressure", "operator": "Exists"},
                    {"key": "node.kubernetes.io/memory-pressure", "operator": "Exists"},
                    {"key": "node.kubernetes.io/not-ready", "operator": "Exists", "effect": "NoExecute"},
                    {"key": "node.kubernetes.io/unreachable", "operator": "Exists", "effect": "NoExecute"},
                    {"key": "node.kubernetes.io/disk-pressure", "operator": "Exists", "effect": "NoSchedule"},
                    {"key": "node.kubernetes.io/memory-pressure", "operator": "Exists", "effect": "NoSchedule"},
                    {"key": "node.kubernetes.io/pid-pressure", "operator": "Exists", "effect": "NoSchedule"},
                    {"key": "node.kubernetes.io/unschedulable", "operator": "Exists", "effect": "NoSchedule"},
                ],
                "containers": [
                    {
                        "name": "eda",
                        "image": image_name,
                        "imagePullPolicy": "IfNotPresent",
                        "securityContext": {"privileged": True},
                        "resources": {
                            "limits": {
                                "cpu": "2",
                                "memory": "4Gi",
                            },
                            "requests": {
                                "cpu": "500m",
                                "memory": "1Gi",
                            },
                        },
                        "envFrom": [
                            {"configMapRef": {"name": "train-service-global-config"}},
                            {"secretRef": {"name": "train-service-secrets"}},
                        ],
                        "env": [{"name": k, "value": str(v)} for k, v in environments.items()],
                        "command": ["bash", "-c", command_str],
                        "volumeMounts": [
                            {"name": "host-train-results", "mountPath": "/wyolo/worker/train_service_results"},
                            {"name": "host-request", "mountPath": "/wyolo/worker/request"},
                            {"name": "host-events", "mountPath": "/wyolo/worker/events"},
                        ],
                    }
                ],
                "volumes": [
                    {
                        "name": "host-train-results",
                        "hostPath": {"path": "/home/wyolo/train_service_results", "type": "DirectoryOrCreate"},
                    },
                    {
                        "name": "host-request",
                        "hostPath": {"path": "/home/wyolo/request", "type": "DirectoryOrCreate"},
                    },
                    {
                        "name": "host-events",
                        "hostPath": {"path": "/home/wyolo/events", "type": "DirectoryOrCreate"},
                    },
                ],
            },
        }

        # Create the Pod
        create_url = f"{self.base_url}/api/v1/namespaces/{self.namespace}/pods"
        resp = requests.post(create_url, headers=self.headers, json=pod_manifest, verify=self.ca_cert, timeout=15)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Failed to create EDA pod {pod_name}: {resp.status_code} - {resp.text}")

        # Wait for Pod completion
        pod_url = f"{self.base_url}/api/v1/namespaces/{self.namespace}/pods/{pod_name}"
        log_url = f"{self.base_url}/api/v1/namespaces/{self.namespace}/pods/{pod_name}/log"

        start_time = time.time()
        timeout = 600  # 10 minutes max for EDA
        output_logs = ""

        try:
            while time.time() - start_time < timeout:
                time.sleep(2)
                status_resp = requests.get(pod_url, headers=self.headers, verify=self.ca_cert, timeout=10)
                if status_resp.status_code == 200:
                    phase = status_resp.json().get("status", {}).get("phase")
                    if phase in ("Succeeded", "Failed"):
                        # Read logs
                        log_resp = requests.get(log_url, headers=self.headers, verify=self.ca_cert, timeout=15)
                        if log_resp.status_code == 200:
                            output_logs = log_resp.text
                        break
        finally:
            self._delete_pod_if_exists(pod_name)

        return output_logs

    def start_executor(
        self,
        image_name: str,
        executor_name: str,
        environments: Dict[str, str],
        volumes: Dict[str, Any],
        command_str: str,
        shm_size_bytes: int,
        mem_limit: int,
        cpu_limit: float,
        results_dir: str,
        timeout_seconds: int,
        invoker_name: str,
        redis_client: Any,
    ) -> int:
        """Start the training executor as a Kubernetes Pod pinned to local node."""
        import uuid

        task_suffix = environments.get("TRIAL_ID") or environments.get("TASK_ID") or ""
        if not task_suffix or task_suffix == "default":
            task_suffix = environments.get("CELERY_TASK_ID", "")[:8]
        if not task_suffix:
            task_suffix = uuid.uuid4().hex[:8]

        base_name = (
            f"{executor_name}-{self.node_name}"
            if self.node_name and self.node_name not in executor_name
            else executor_name
        )
        pod_name = sanitize_k8s_name(f"{base_name}-{task_suffix}")
        self._delete_pod_if_exists(pod_name)

        trial_id = environments.get("TRIAL_ID", "default")
        # Ensure SHM is bounded between 2Gi and 8Gi to prevent host swap thrashing
        if shm_size_bytes > 0:
            shm_gb = max(2, min(8, int(shm_size_bytes / (1024**3))))
        else:
            shm_gb = 4

        # Safe memory limit: min 4Gi, fallback 16Gi
        mem_gb = max(4, int(mem_limit / (1024**3))) if mem_limit > 0 else 16
        cpu_val = max(1, int(cpu_limit)) if cpu_limit > 0 else 4

        # Defensive thread limits to prevent multi-threading CPU freeze
        max_threads = str(min(4, max(1, cpu_val)))
        thread_vars = {
            "OMP_NUM_THREADS": max_threads,
            "MKL_NUM_THREADS": max_threads,
            "OPENBLAS_NUM_THREADS": max_threads,
            "VECLIB_MAXIMUM_THREADS": max_threads,
            "NUMEXPR_NUM_THREADS": max_threads,
            "TORCH_NUM_THREADS": max_threads,
        }
        for var_name, var_val in thread_vars.items():
            if var_name not in environments:
                environments[var_name] = var_val

        print(
            f"--- [INVOKER][K8s] Spawning Executor Pod '{pod_name}' on node '{self.node_name}' (Image: {image_name}) ---",
            flush=True,
        )

        gpu_req = environments.get("GPU_COUNT") or (
            self.config.get("gpu_count") if isinstance(self.config, dict) else "1"
        )
        gpu_str = str(gpu_req) if str(gpu_req).isdigit() and int(gpu_req) > 0 else "1"

        if environments.get("NVIDIA_VISIBLE_DEVICES") in ("void", None, ""):
            environments["NVIDIA_VISIBLE_DEVICES"] = "0"
        environments["NVIDIA_DRIVER_CAPABILITIES"] = "all"

        pod_manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": pod_name,
                "namespace": self.namespace,
                "labels": {
                    "app": "wyolo-executor",
                    "node": self.node_name,
                    "trial_id": str(trial_id),
                },
            },
            "spec": {
                "nodeName": self.node_name,
                "restartPolicy": "Never",
                "activeDeadlineSeconds": max(1, int(timeout_seconds)),
                "tolerations": [
                    {"key": "nvidia.com/gpu", "operator": "Exists", "effect": "NoSchedule"},
                    {"key": "node.kubernetes.io/disk-pressure", "operator": "Exists"},
                    {"key": "node.kubernetes.io/memory-pressure", "operator": "Exists"},
                    {"key": "node.kubernetes.io/not-ready", "operator": "Exists", "effect": "NoExecute"},
                    {"key": "node.kubernetes.io/unreachable", "operator": "Exists", "effect": "NoExecute"},
                    {"key": "node.kubernetes.io/disk-pressure", "operator": "Exists", "effect": "NoSchedule"},
                    {"key": "node.kubernetes.io/memory-pressure", "operator": "Exists", "effect": "NoSchedule"},
                    {"key": "node.kubernetes.io/pid-pressure", "operator": "Exists", "effect": "NoSchedule"},
                    {"key": "node.kubernetes.io/unschedulable", "operator": "Exists", "effect": "NoSchedule"},
                ],
                "containers": [
                    {
                        "name": "executor",
                        "image": image_name,
                        "imagePullPolicy": "IfNotPresent",
                        "securityContext": {"privileged": True},
                        "envFrom": [
                            {"configMapRef": {"name": "train-service-global-config"}},
                            {"secretRef": {"name": "train-service-secrets"}},
                        ],
                        "env": [{"name": k, "value": str(v)} for k, v in environments.items()],
                        "resources": {
                            "limits": {
                                "nvidia.com/gpu": gpu_str,
                                "memory": f"{mem_gb}Gi",
                                "cpu": str(cpu_val),
                            },
                            "requests": {
                                "nvidia.com/gpu": gpu_str,
                                "memory": f"{max(2, min(4, mem_gb // 2))}Gi",
                                "cpu": "1",
                            },
                        },
                        "command": ["bash", "-c", command_str],
                        "volumeMounts": [
                            {"name": "dshm", "mountPath": "/dev/shm"},  # nosec B108
                            {"name": "host-train-results", "mountPath": "/wyolo/worker/train_service_results"},
                            {"name": "host-request", "mountPath": "/wyolo/worker/request"},
                            {"name": "host-events", "mountPath": "/wyolo/worker/events"},
                        ],
                    }
                ],
                "volumes": [
                    {
                        "name": "dshm",
                        "emptyDir": {"medium": "Memory", "sizeLimit": f"{shm_gb}Gi"},
                    },
                    {
                        "name": "host-train-results",
                        "hostPath": {"path": "/home/wyolo/train_service_results", "type": "DirectoryOrCreate"},
                    },
                    {
                        "name": "host-request",
                        "hostPath": {"path": "/home/wyolo/request", "type": "DirectoryOrCreate"},
                    },
                    {
                        "name": "host-events",
                        "hostPath": {"path": "/home/wyolo/events", "type": "DirectoryOrCreate"},
                    },
                ],
            },
        }

        # Create the Pod
        create_url = f"{self.base_url}/api/v1/namespaces/{self.namespace}/pods"
        resp = requests.post(create_url, headers=self.headers, json=pod_manifest, verify=self.ca_cert, timeout=15)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Failed to create Executor pod {pod_name}: {resp.status_code} - {resp.text}")

        print(f"--- [INVOKER][K8s] Pod {pod_name} created successfully. Waiting for container start... ---", flush=True)

        pod_url = f"{self.base_url}/api/v1/namespaces/{self.namespace}/pods/{pod_name}"
        log_url = f"{self.base_url}/api/v1/namespaces/{self.namespace}/pods/{pod_name}/log?follow=true"

        # Wait until Pod enters Running state or finishes
        start_wait = time.time()
        while time.time() - start_wait < 300:
            try:
                status_resp = requests.get(pod_url, headers=self.headers, verify=self.ca_cert, timeout=10)
                if status_resp.status_code == 200:
                    phase = status_resp.json().get("status", {}).get("phase")
                    if phase in ("Running", "Succeeded", "Failed"):
                        break
                elif status_resp.status_code == 404:
                    raise RuntimeError(f"Executor pod {pod_name} was deleted before it could start.")
            except requests.exceptions.RequestException:
                pass
            time.sleep(1)

        print(f"--- [INVOKER][K8s] Executor Pod {pod_name} is running. Streaming logs in real-time... ---", flush=True)

        stop_event = threading.Event()
        user_deleted = False
        log_file_path = os.path.join(results_dir, f"logs_{executor_name}.txt")

        task_id = environments.get("TASK_ID") or environments.get("CELERY_TASK_ID")
        study_id = environments.get("STUDY_ID")

        def check_k8s_cancellation() -> bool:
            """Check Redis for cancellation requests targeting this task, study, or host node drain."""
            if not redis_client:
                return False
            try:
                keys = []
                if task_id:
                    keys.extend([f"wyolo:task:{task_id}:cancel", f"task:{task_id}:cancel"])
                if study_id:
                    keys.extend(
                        [f"study:{study_id}:cancel", f"wyolo:study:{study_id}:cancel", f"study:{study_id}:cancelled"]
                    )
                # Check host node-level drain or eviction
                worker_ip = environments.get("WORKER_HOST") or os.getenv("WORKER_HOST")
                if worker_ip:
                    keys.append(f"invoker:{worker_ip}:cancel_active")
                    drain_val = redis_client.get(f"invoker:{worker_ip}:drain")
                    if drain_val:
                        try:
                            drain_data = json.loads(drain_val.decode() if isinstance(drain_val, bytes) else drain_val)
                            if drain_data.get("draining") and drain_data.get("evict", True):
                                return True
                        except Exception:
                            pass
                for k in keys:
                    if redis_client.get(k):
                        return True
            except Exception:
                pass
            return False

        def get_k8s_pod_metrics() -> Tuple[float, float, float]:
            """Retrieve real CPU, RAM (MB), and GPU utilization for the K8s pod."""
            cpu_val_metric = 0.0
            ram_val_metric = 0.0
            gpu_val_metric = get_gpu_utilization("0")

            try:
                metrics_url = f"{self.base_url}/apis/metrics.k8s.io/v1beta1/namespaces/{self.namespace}/pods/{pod_name}"
                m_resp = requests.get(metrics_url, headers=self.headers, verify=self.ca_cert, timeout=3)
                if m_resp.status_code == 200:
                    c_metrics = m_resp.json().get("containers", [])
                    if c_metrics:
                        usage = c_metrics[0].get("usage", {})
                        cpu_raw = usage.get("cpu", "0")
                        if cpu_raw.endswith("n"):
                            cpu_val_metric = round(float(cpu_raw[:-1]) / 1e9 * 100.0, 2)
                        elif cpu_raw.endswith("m"):
                            cpu_val_metric = round(float(cpu_raw[:-1]) / 10.0, 2)

                        mem_raw = usage.get("memory", "0")
                        if mem_raw.endswith("Ki"):
                            ram_val_metric = round(float(mem_raw[:-2]) / 1024.0, 2)
                        elif mem_raw.endswith("Mi"):
                            ram_val_metric = round(float(mem_raw[:-2]), 2)
                        elif mem_raw.endswith("Gi"):
                            ram_val_metric = round(float(mem_raw[:-2]) * 1024.0, 2)
            except Exception:
                pass
            return cpu_val_metric, ram_val_metric, gpu_val_metric

        def get_k8s_current_epoch() -> str:
            """Extract current epoch from Kubernetes pod logs."""
            try:
                resp = requests.get(
                    f"{self.base_url}/api/v1/namespaces/{self.namespace}/pods/{pod_name}/log?tailLines=50",
                    headers=self.headers,
                    verify=self.ca_cert,
                    timeout=5,
                )
                if resp.status_code == 200:
                    matches = re.findall(r"\s+(\d+)/\d+\s+\d+\.\d+G", resp.text)
                    if matches:
                        return matches[-1]
            except Exception:
                pass
            return "N/A"

        def monitor_k8s_pod() -> None:
            """Monitor Kubernetes Pod phase and write telemetry."""
            nonlocal user_deleted
            while not stop_event.is_set():
                try:
                    if check_k8s_cancellation():
                        user_deleted = True
                        print(
                            f"⚠️ [INVOKER][K8s] Cancellation signal detected for pod {pod_name}. Deleting pod...",
                            flush=True,
                        )
                        self._delete_pod_if_exists(pod_name)
                        break

                    p_resp = requests.get(pod_url, headers=self.headers, verify=self.ca_cert, timeout=10)
                    if p_resp.status_code == 404:
                        user_deleted = True
                        print(
                            f"--- [INVOKER][K8s] Executor Pod {pod_name} was deleted from outside (Dozzle/K8s). ---",
                            flush=True,
                        )
                        break

                    data = p_resp.json().get("status", {})
                    phase = data.get("phase", "Unknown")

                    real_cpu, real_ram, real_gpu = get_k8s_pod_metrics()

                    stats_payload = {
                        "status": "cancelled" if user_deleted else ("running" if phase == "Running" else phase.lower()),
                        "cpu": real_cpu,
                        "ram_mb": real_ram,
                        "gpu": real_gpu,
                        "epoch": get_k8s_current_epoch(),
                        "timestamp": time.time(),
                    }
                    if redis_client:
                        redis_client.set(
                            f"executor:{executor_name}:stats",
                            json.dumps(stats_payload),
                            ex=30,
                        )
                    if results_dir:
                        telemetry_file = os.path.join(results_dir, f"telemetry_{executor_name}.json")
                        tmp_file = telemetry_file + ".tmp"
                        try:
                            with open(tmp_file, "w", encoding="utf-8") as f:
                                json.dump(stats_payload, f, indent=4)
                            os.replace(tmp_file, telemetry_file)
                        except Exception:
                            pass
                except Exception:
                    pass
                if stop_event.wait(2.0):
                    break

        def stream_logs() -> None:
            """Stream pod logs in real-time with automatic reconnection."""
            last_log_time = time.time()
            reconnecting = False
            while not stop_event.is_set():
                try:
                    query_url = log_url
                    if reconnecting:
                        since_sec = max(1, int(time.time() - last_log_time) + 2)
                        query_url = f"{log_url}&sinceSeconds={since_sec}"
                    with requests.get(
                        query_url,
                        headers=self.headers,
                        verify=self.ca_cert,
                        stream=True,
                        timeout=30,
                    ) as resp:
                        if resp.status_code == 200:
                            for line in resp.iter_lines():
                                if stop_event.is_set():
                                    break
                                if line:
                                    last_log_time = time.time()
                                    decoded = line.decode("utf-8", errors="replace").rstrip()
                                    print(f"[{pod_name}] {decoded}", flush=True)
                                    with open(log_file_path, "a", encoding="utf-8") as log_file:
                                        log_file.write(decoded + "\n")
                                        log_file.flush()
                except Exception:
                    if stop_event.is_set():
                        break
                reconnecting = True
                if stop_event.wait(2.0):
                    break

        # Initialize empty log file
        with open(log_file_path, "w", encoding="utf-8"):
            pass

        monitor_thread = threading.Thread(target=monitor_k8s_pod, daemon=True)
        log_thread = threading.Thread(target=stream_logs, daemon=True)
        monitor_thread.start()
        log_thread.start()

        exit_code = 1
        start_wait_terminal = time.time()
        try:
            while time.time() - start_wait_terminal < timeout_seconds:
                if user_deleted:
                    raise RuntimeError(f"Executor pod {pod_name} was deleted/cancelled by user.")
                try:
                    final_resp = requests.get(pod_url, headers=self.headers, verify=self.ca_cert, timeout=10)
                    if final_resp.status_code == 200:
                        p_status = final_resp.json().get("status", {})
                        phase = p_status.get("phase", "Unknown")
                        if phase in ("Succeeded", "Failed"):
                            container_statuses = p_status.get("containerStatuses", [])
                            if container_statuses:
                                term_state = container_statuses[0].get("state", {}).get("terminated", {})
                                exit_code = term_state.get("exitCode", 0 if phase == "Succeeded" else 1)
                            else:
                                exit_code = 0 if phase == "Succeeded" else 1
                            if phase == "Failed":
                                fail_msg = p_status.get("message") or p_status.get("reason")
                                if fail_msg:
                                    print(f"--- [INVOKER][K8s] Pod {pod_name} failed: {fail_msg} ---", flush=True)
                                    with open(log_file_path, "a", encoding="utf-8") as log_file:
                                        log_file.write(f"\n--- [K8s Pod Failure Reason: {fail_msg}] ---\n")
                                        log_file.flush()
                            break
                    elif final_resp.status_code == 404:
                        user_deleted = True
                        raise RuntimeError(f"Executor pod {pod_name} was deleted/cancelled by user.")
                except requests.exceptions.RequestException:
                    pass
                if stop_event.wait(2.0):
                    break
            else:
                exit_code = 124
                raise TimeoutError(
                    f"Executor pod {pod_name} exceeded timeout of {timeout_seconds}s without terminating."
                )
        finally:
            stop_event.set()
            monitor_thread.join(timeout=2)
            log_thread.join(timeout=3)

        # Capture failure logs if exit_code != 0
        if exit_code != 0 and results_dir:
            try:
                tail_resp = requests.get(
                    f"{self.base_url}/api/v1/namespaces/{self.namespace}/pods/{pod_name}/log?tailLines=200",
                    headers=self.headers,
                    verify=self.ca_cert,
                    timeout=5,
                )
                if tail_resp.status_code == 200 and tail_resp.text:
                    with open(log_file_path, "a", encoding="utf-8") as log_file:
                        log_file.write(f"\n--- [K8s Pod Final Failure Logs (ExitCode: {exit_code})] ---\n")
                        log_file.write(tail_resp.text)
                        log_file.flush()
            except Exception as log_err:
                print(f"--- [INVOKER][K8s] Could not capture final logs: {log_err} ---")

        # Cleanup Pod post-execution
        self._delete_pod_if_exists(pod_name)

        if results_dir:
            telemetry_file = os.path.join(results_dir, f"telemetry_{executor_name}.json")
            try:
                with open(telemetry_file, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "status": "finished",
                            "cpu": 0,
                            "ram_mb": 0,
                            "gpu": 0.0,
                            "timestamp": time.time(),
                        },
                        f,
                        indent=4,
                    )
            except Exception:
                pass

        return exit_code


def get_orchestrator(config: Optional[Dict[str, Any]] = None) -> BaseOrchestrator:
    """Factory function returning the active Orchestrator based on environment."""
    if is_k8s_environment():
        print("=== [ORCHESTRATOR] Operating in KUBERNETES mode (Native Pod Lifecycle) ===", flush=True)
        return KubernetesOrchestrator(config)
    print("=== [ORCHESTRATOR] Operating in DOCKER mode (Local Daemon Lifecycle) ===", flush=True)
    return DockerOrchestrator(config)
