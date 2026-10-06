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

        container = self.client.containers.run(
            image=image_name,
            name=executor_name,
            hostname=environments.get("USER", "default_user"),
            detach=True,
            remove=False,
            privileged=True,
            network_mode="host",
            shm_size=shm_size_bytes,
            tty=False,
            nano_cpus=int(cpu_limit * 1e9),
            mem_limit=mem_limit,
            cap_add=["SYS_ADMIN", "DAC_READ_SEARCH", "NET_ADMIN", "SYS_RESOURCE"],
            device_requests=[docker.types.DeviceRequest(device_ids=["0"], capabilities=[["gpu"]])],
            environment=environments,
            labels={
                "autoheal": "true",
                "com.centurylinklabs.watchtower.enable": "true",
            },
            volumes=volumes,
            command=command_str,
        )

        print(f"--- [INVOKER][Docker] Executor {executor_name} started. Streaming logs... ---", flush=True)

        stop_monitor = False
        log_file_path = os.path.join(results_dir, f"logs_{executor_name}.txt")

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
            """Monitor container resource usage and write telemetry."""
            while not stop_monitor:
                try:
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

                    stats_payload = {
                        "status": "running",
                        "cpu": round(cpu_percent, 2),
                        "ram_mb": round(ram_mb, 2),
                        "gpu": 0.0,
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

    def run_eda(
        self,
        image_name: str,
        name: str,
        environments: Dict[str, str],
        volumes: Dict[str, Any],
        command: List[str],
    ) -> str:
        """Run temporary EDA Pod using in-cluster Kubernetes API."""
        pod_name = sanitize_k8s_name(name)
        self._delete_pod_if_exists(pod_name)

        command_str = " ".join(command) if isinstance(command, list) else str(command)

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
                "containers": [
                    {
                        "name": "eda",
                        "image": image_name,
                        "imagePullPolicy": "IfNotPresent",
                        "securityContext": {"privileged": True},
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
        pod_name = sanitize_k8s_name(executor_name)
        self._delete_pod_if_exists(pod_name)

        trial_id = environments.get("TRIAL_ID", "default")
        shm_gb = max(16, int(shm_size_bytes / (1024**3)))
        mem_gb = max(16, int(mem_limit / (1024**3))) if mem_limit > 0 else 32
        cpu_val = max(2, int(cpu_limit)) if cpu_limit > 0 else 4

        print(
            f"--- [INVOKER][K8s] Spawning Executor Pod '{pod_name}' on node '{self.node_name}' (Image: {image_name}) ---",
            flush=True,
        )

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
                "containers": [
                    {
                        "name": "executor",
                        "image": image_name,
                        "imagePullPolicy": "IfNotPresent",
                        "securityContext": {"privileged": True},
                        "env": [{"name": k, "value": str(v)} for k, v in environments.items()],
                        "resources": {
                            "limits": {
                                "nvidia.com/gpu": "1",
                                "memory": f"{mem_gb}Gi",
                                "cpu": str(cpu_val),
                            },
                            "requests": {
                                "nvidia.com/gpu": "1",
                                "memory": "4Gi",
                                "cpu": "2",
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

        stop_monitor = False
        user_deleted = False
        log_file_path = os.path.join(results_dir, f"logs_{executor_name}.txt")

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

        def monitor_k8s_pod():
            """Monitor Kubernetes Pod phase and write telemetry."""
            nonlocal user_deleted
            while not stop_monitor:
                try:
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

                    stats_payload = {
                        "status": "running" if phase == "Running" else phase.lower(),
                        "cpu": 0.0,
                        "ram_mb": 0.0,
                        "gpu": 0.0,
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
                time.sleep(2)

        monitor_thread = threading.Thread(target=monitor_k8s_pod, daemon=True)
        monitor_thread.start()

        exit_code = 0
        try:
            with open(log_file_path, "w", encoding="utf-8") as log_file:
                # Stream logs via chunked HTTP stream
                log_stream_resp = requests.get(
                    log_url,
                    headers=self.headers,
                    verify=self.ca_cert,
                    stream=True,
                    timeout=timeout_seconds,
                )
                if log_stream_resp.status_code == 200:
                    for line in log_stream_resp.iter_lines():
                        if line:
                            decoded = line.decode("utf-8", errors="replace").rstrip()
                            print(f"[{pod_name}] {decoded}", flush=True)
                            log_file.write(decoded + "\n")
                            log_file.flush()
        except Exception as exc:
            print(f"--- [INVOKER][K8s] Log streaming ended: {exc} ---", flush=True)
        finally:
            stop_monitor = True
            monitor_thread.join(timeout=2)

        # Check final Pod status
        try:
            final_resp = requests.get(pod_url, headers=self.headers, verify=self.ca_cert, timeout=10)
            if final_resp.status_code == 200:
                p_status = final_resp.json().get("status", {})
                container_statuses = p_status.get("containerStatuses", [])
                if container_statuses:
                    term_state = container_statuses[0].get("state", {}).get("terminated", {})
                    exit_code = term_state.get("exitCode", 0)
                elif p_status.get("phase") == "Failed":
                    exit_code = 1
            elif final_resp.status_code == 404 or user_deleted:
                raise RuntimeError(f"Executor pod {pod_name} was deleted/cancelled by user.")
        except Exception as exc:
            if user_deleted or "deleted" in str(exc).lower():
                raise RuntimeError(f"Executor pod {pod_name} was deleted/cancelled by user.") from exc

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
