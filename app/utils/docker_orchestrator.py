"""Docker-based execution orchestrator for worker invoker."""

from typing import Any, Dict, List, Optional
from .docker_monitor import run_monitored_docker_container
from .orchestrator_base import BaseOrchestrator, get_optimal_gpu_device


class DockerOrchestrator(BaseOrchestrator):
    """Orchestrates tasks via the local Docker daemon."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize DockerOrchestrator with configuration.

        Args:
            config (Optional[Dict[str, Any]]): Invoker configuration dictionary.
        """
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
        """Run temporary EDA container using local Docker daemon.

        Args:
            image_name (str): Container image name.
            name (str): Container instance name.
            environments (Dict[str, str]): Environment variables.
            volumes (Dict[str, Any]): Mounted volumes mapping.
            command (List[str]): Command arguments.

        Returns:
            str: Output logs decoded to string.
        """
        try:
            self.client.containers.get(name).remove(force=True)
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
        """Sweep and remove lingering wyolo executor and eda containers.

        Returns:
            int: Number of removed containers.
        """
        cleaned = 0
        try:
            for c in self.client.containers.list(all=True):
                c_name = str(vars(c).get("name", "") or c.name)
                if c_name and (c_name.startswith("wyolo_executor_") or c_name.startswith("wyolo_eda_runner_")):
                    try:
                        c.remove(force=True)
                        cleaned += 1
                    except Exception:
                        pass
        except Exception:
            pass
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
        """Start the training executor container and stream logs.

        Args:
            image_name (str): Container image to spawn.
            executor_name (str): Unique container name.
            environments (Dict[str, str]): Environment variables.
            volumes (Dict[str, Any]): Host volume bindings.
            command_str (str): Shell command to execute.
            shm_size_bytes (int): Shared memory size in bytes.
            mem_limit (int): Memory limit in bytes.
            cpu_limit (float): Max CPU cores limit.
            results_dir (str): Base output directory.
            timeout_seconds (int): Execution timeout in seconds.
            invoker_name (str): Identifier of the executing worker invoker.
            redis_client (Any): Connected Redis client.

        Returns:
            int: Container exit code.

        Raises:
            RuntimeError: If the container fails or times out.
        """
        import docker  # type: ignore

        try:
            self.client.containers.get(executor_name).remove(force=True)
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

        cpu_val = max(1, int(cpu_limit)) if cpu_limit > 0 else 2
        max_threads = str(min(4, max(1, cpu_val)))
        for var_name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "TORCH_NUM_THREADS"):
            environments.setdefault(var_name, max_threads)

        run_kwargs: Dict[str, Any] = {
            "image": image_name,
            "name": executor_name,
            "command": ["/bin/bash", "-c", command_str],
            "environment": environments,
            "volumes": volumes,
            "shm_size": shm_size_bytes,
            "mem_limit": mem_limit,
            "device_requests": dev_requests,
            "network_mode": "host",
            "ipc_mode": "host",
            "privileged": True,
            "detach": True,
        }
        if cpu_limit > 0:
            run_kwargs["nano_cpus"] = int(cpu_limit * 1e9)

        container = self.client.containers.run(**run_kwargs)
        return run_monitored_docker_container(
            container, executor_name, results_dir, timeout_seconds, environments, selected_gpus, redis_client
        )
