"""Kubernetes-based execution orchestrator for worker invoker."""

import os
import time
from typing import Any, Dict, List, Optional
import requests
from .k8s_manifest_builder import build_k8s_pod_manifest
from .k8s_monitor import delete_k8s_pod_safely, wait_for_k8s_pod_completion
from .orchestrator_base import BaseOrchestrator, sanitize_k8s_name


class KubernetesOrchestrator(BaseOrchestrator):
    """Orchestrates tasks directly as Kubernetes Pods using in-cluster API."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize KubernetesOrchestrator with cluster credentials.

        Args:
            config (Optional[Dict[str, Any]]): Invoker configuration dictionary.
        """
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
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

        ns_file = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
        if os.path.exists(ns_file):
            with open(ns_file, "r", encoding="utf-8") as f:
                self.namespace = f.read().strip()
        else:
            self.namespace = os.getenv("K8S_NAMESPACE", "train-service")
        self.node_name = os.getenv("WORKER_HOSTNAME") or os.getenv("K8S_NODE_NAME") or ""

    def clean_orphaned_tasks(self) -> int:
        """Sweep and remove lingering wyolo executor and eda pods on this node.

        Returns:
            int: Number of deleted pods.
        """
        cleaned = 0
        try:
            url = f"{self.base_url}/api/v1/namespaces/{self.namespace}/pods?labelSelector=app in (wyolo-executor,wyolo-eda)"
            resp = requests.get(url, headers=self.headers, verify=self.ca_cert, timeout=10)
            if resp.status_code == 200:
                for pod in resp.json().get("items", []):
                    p_node = pod.get("spec", {}).get("nodeName", "")
                    p_name = pod.get("metadata", {}).get("name", "")
                    if not self.node_name or p_node == self.node_name:
                        delete_k8s_pod_safely(self.base_url, self.namespace, p_name, self.headers, self.ca_cert)
                        cleaned += 1
        except Exception:
            pass
        return cleaned

    def run_eda(
        self,
        image_name: str,
        name: str,
        environments: Dict[str, str],
        volumes: Dict[str, Any],
        command: List[str],
    ) -> str:
        """Run temporary EDA Pod using in-cluster Kubernetes API.

        Args:
            image_name (str): Docker image name.
            name (str): Pod instance base name.
            environments (Dict[str, str]): Runtime environment variables.
            volumes (Dict[str, Any]): Mounted host directories.
            command (List[str]): CLI command arguments.

        Returns:
            str: EDA stdout output log.
        """
        pod_name = sanitize_k8s_name(f"{name}-{self.node_name}")
        delete_k8s_pod_safely(self.base_url, self.namespace, pod_name, self.headers, self.ca_cert)
        cmd_str = " ".join(command) if isinstance(command, list) else str(command)
        environments.setdefault("NVIDIA_VISIBLE_DEVICES", "0")
        environments["NVIDIA_DRIVER_CAPABILITIES"] = "all"

        manifest = build_k8s_pod_manifest(
            pod_name, self.namespace, self.node_name, image_name, cmd_str, environments, volumes, 2, 4, 2.0, 600, "eda", "1"
        )
        url = f"{self.base_url}/api/v1/namespaces/{self.namespace}/pods"
        requests.post(url, headers=self.headers, json=manifest, verify=self.ca_cert, timeout=15)

        for _ in range(60):
            time.sleep(2)
            chk = requests.get(f"{url}/{pod_name}", headers=self.headers, verify=self.ca_cert, timeout=5)
            if chk.status_code == 200 and chk.json().get("status", {}).get("phase") in ("Succeeded", "Failed"):
                break

        log_resp = requests.get(f"{url}/{pod_name}/log", headers=self.headers, verify=self.ca_cert, timeout=10)
        out = log_resp.text if log_resp.status_code == 200 else ""
        delete_k8s_pod_safely(self.base_url, self.namespace, pod_name, self.headers, self.ca_cert)
        return out

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
        """Start the training executor as a Kubernetes Pod pinned to local node.

        Args:
            image_name (str): Container image to spawn.
            executor_name (str): Pod instance identifier.
            environments (Dict[str, str]): Environment variables.
            volumes (Dict[str, Any]): Mounted directories.
            command_str (str): Bash command string.
            shm_size_bytes (int): Shared memory size in bytes.
            mem_limit (int): Memory restriction in bytes.
            cpu_limit (float): Max CPU cores allowed.
            results_dir (str): Base output directory.
            timeout_seconds (int): Watchdog timeout.
            invoker_name (str): Node name.
            redis_client (Any): Connected Redis client.

        Returns:
            int: Pod execution exit code.
        """
        task_suffix = environments.get("TRIAL_ID") or environments.get("TASK_ID") or "default"
        pod_name = sanitize_k8s_name(f"{executor_name}-{self.node_name}-{task_suffix}")
        delete_k8s_pod_safely(self.base_url, self.namespace, pod_name, self.headers, self.ca_cert)

        shm_gb = max(2, min(8, int(shm_size_bytes / (1024**3)))) if shm_size_bytes > 0 else 4
        mem_gb = max(4, int(mem_limit / (1024**3))) if mem_limit > 0 else 16
        gpu_str = str(environments.get("GPU_COUNT", "1"))
        trial_id = str(environments.get("TRIAL_ID", "default"))

        manifest = build_k8s_pod_manifest(
            pod_name, self.namespace, self.node_name, image_name, command_str, environments, volumes,
            shm_gb, mem_gb, cpu_limit, timeout_seconds, trial_id, gpu_str
        )
        url = f"{self.base_url}/api/v1/namespaces/{self.namespace}/pods"
        requests.post(url, headers=self.headers, json=manifest, verify=self.ca_cert, timeout=15)
        return wait_for_k8s_pod_completion(
            self.base_url, self.namespace, pod_name, executor_name, results_dir, timeout_seconds, environments, redis_client, self.headers, self.ca_cert
        )
