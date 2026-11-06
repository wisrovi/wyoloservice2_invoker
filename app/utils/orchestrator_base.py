"""Base orchestrator definitions and GPU/Environment detection utilities."""

import os
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple


def is_k8s_environment() -> bool:
    """Detect if running inside a Kubernetes cluster environment.

    Returns:
        bool: True if inside Kubernetes, False otherwise.
    """
    orch = os.getenv("ORCHESTRATOR", "").strip().lower()
    if orch in ("k8s", "kubernetes"):
        return True
    if orch == "docker":
        return False
    token_file = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    return bool(os.getenv("KUBERNETES_SERVICE_HOST")) and os.path.exists(token_file)


def sanitize_k8s_name(name: str) -> str:
    """Sanitize container/trial name into a valid Kubernetes DNS-1123 label.

    Args:
        name (str): Raw trial or container identifier.

    Returns:
        str: DNS-1123 valid string up to 63 characters.
    """
    sanitized = re.sub(r"[^a-z0-9\-]", "-", name.lower()).strip("-")
    sanitized = re.sub(r"-+", "-", sanitized)
    if not sanitized:
        sanitized = "wyolo-task"
    return sanitized[:63]


def get_optimal_gpu_device(preferred_gpu: Optional[str] = None) -> List[str]:
    """Determine the optimal target GPU device ID(s) for task execution.

    Args:
        preferred_gpu (Optional[str]): Optional override specifying GPU index or 'all'.

    Returns:
        List[str]: Selected GPU index strings, or ['all'].
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
        target_gpu (str): Target GPU index string or 'all'.

    Returns:
        float: Utilization percentage between 0.0 and 100.0.
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
    """Abstract interface defining contract for task orchestrators."""

    def run_eda(
        self,
        image_name: str,
        name: str,
        environments: Dict[str, str],
        volumes: Dict[str, Any],
        command: List[str],
    ) -> str:
        """Run temporary EDA container/pod and return stdout string.

        Args:
            image_name (str): Target container image.
            name (str): Instance name.
            environments (Dict[str, str]): Environment variables.
            volumes (Dict[str, Any]): Mounted volumes mapping.
            command (List[str]): Execution arguments.

        Returns:
            str: Standard output from execution.

        Raises:
            NotImplementedError: If not implemented by child class.
        """
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
        """Run training executor container/pod and return exit code.

        Args:
            image_name (str): Target container image.
            executor_name (str): Unique instance name.
            environments (Dict[str, str]): Runtime environment variables.
            volumes (Dict[str, Any]): Host volume mount paths.
            command_str (str): Shell command to execute.
            shm_size_bytes (int): Shared memory size in bytes.
            mem_limit (int): Memory restriction in bytes.
            cpu_limit (float): Max CPU cores allowed.
            results_dir (str): Output directory on host.
            timeout_seconds (int): Execution timeout in seconds.
            invoker_name (str): Worker identifier.
            redis_client (Any): Connected Redis client for stats and cancellation.

        Returns:
            int: Process exit code (0 for success).

        Raises:
            NotImplementedError: If not implemented by child class.
        """
        raise NotImplementedError

    def clean_orphaned_tasks(self) -> int:
        """Sweep and remove lingering executor and eda containers or pods.

        Returns:
            int: Number of orphaned items removed.

        Raises:
            NotImplementedError: If not implemented by child class.
        """
        raise NotImplementedError
