"""Run Training State Module.

This module defines the RunTraining class, which orchestrates the execution
of training trials within Docker containers. It handles configuration delivery,
container management, and results recovery.
"""

import os
import json
import tempfile
import shutil
import multiprocessing
from typing import Any, Dict
from datetime import datetime

import docker  # pylint: disable=import-error


DEFAULT_TRAIN_IMAGE = "wisrovi/train_service:worker_executor_v1.0.0"


def get_system_limits(config: Dict[str, Any]):
    """Calculates the hardware limits based on the host system and config.

    Args:
        config (Dict[str, Any]): The worker configuration dictionary.

    Returns:
        tuple: (cpu_limit, mem_limit_bytes)
    """
    cpu_pct = float(config.get("cpu_limit_pct", 0.85))
    mem_pct = float(config.get("mem_limit_pct", 0.60))

    # 1. CPU: Percentage of total cores
    total_cpus = multiprocessing.cpu_count()
    cpu_limit = float(total_cpus * cpu_pct)

    # 2. RAM: Percentage of total host memory
    total_mem_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    mem_limit_bytes = int(total_mem_bytes * mem_pct)

    return cpu_limit, mem_limit_bytes



class RunTraining:
    """Orchestrates the execution of a training trial in a Docker container.

    This class manages the lifecycle of a training execution, from setting up
    a temporary workspace to retrieving the final metrics from the executor.

    Attributes:
        NAME (str): The name of the module.
        VERSION (str): The version of the module.
        config (Dict[str, Any]): Configuration dictionary for the training process.
    """

    NAME: str = __name__
    VERSION: str = "1.0.0"

    def __init__(self, config: Dict[str, Any]):
        """Initializes the RunTraining instance.

        Args:
            config (Dict[str, Any]): Configuration dictionary containing executor settings.
        """
        self.config = config

    def docker_run(self, image_name: str, executor_name: str, temp_dir: str) -> None:
        """Runs a Docker container with the specified configuration.

        Args:
            image_name (str): The name of the Docker image to run.
            executor_name (str): The name to assign to the running container.
            temp_dir (str): The local directory to bind as a volume.
        """

        invoker_name = os.getenv("PRIVATE_QUEUE", "unknown")

        # Calculate hardware limits dynamically from config
        cpu_limit, mem_limit = get_system_limits(self.config)

        print(
            f"--- [INVOKER:{invoker_name}] Launching executor: {executor_name} with limits (CPU: {cpu_limit:.2f}, RAM: {mem_limit // (1024**2)}MB) ---"
        )

        try:
            client = docker.from_env()
        except Exception as exc:
            print(
                f"--- [INVOKER:{os.getenv('PRIVATE_QUEUE', 'unknown')}] Unexpected error: {exc} ---"
            )
            raise exc

        try:
            # Resource constraints configuration
            client.containers.run(
                image=image_name,
                name=executor_name,
                detach=False,
                remove=True,
                # Sharing all GPUs
                device_requests=[
                    docker.types.DeviceRequest(count=-1, capabilities=[["gpu"]])
                ],
                # Hardware limits
                mem_limit=f"{mem_limit}",
                nano_cpus=int(cpu_limit * 1e9),
                # Persistence and isolation
                volumes={temp_dir: {"bind": "/app/data", "mode": "rw"}},
            )
        except Exception as exc:
            print(
                f"--- [INVOKER:{os.getenv('PRIVATE_QUEUE', 'unknown')}] Unexpected error: {exc} ---"
            )
            raise exc

    def __call__(self, training_config: Dict[str, Any]) -> Dict[str, Any]:
        """Executes the training trial.

        This method sets up the environment, runs the executor container,
        and recovers the metrics.

        Args:
            training_config (Dict[str, Any]): Configuration for the specific training trial.

        Returns:
            Dict[str, Any]: A dictionary containing the execution status and results.

        Raises:
            FileNotFoundError: If results.json is not found after execution.
            RuntimeError: If the executor container fails.
            Exception: For any other unexpected errors.
        """

        invoker_name = os.getenv("PRIVATE_QUEUE", "unknown")

        temp_dir: str = tempfile.mkdtemp(prefix="trial_", dir="/tmp")
        os.chmod(temp_dir, 0o777)

        try:
            # 1. Deliver Config: Write the JSON config to a file for the executor
            config_path: str = os.path.join(temp_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as file:
                json.dump(training_config, file)

            # 2. Run the EXECUTOR
            self.docker_run(
                image_name=self.config.get("executor_image", DEFAULT_TRAIN_IMAGE),
                executor_name=f"{invoker_name}_son_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                temp_dir=temp_dir,
            )

            # 3. Recover Metric: Optuna needs the accuracy to proceed
            result_path: str = os.path.join(temp_dir, "results.json")
            if os.path.exists(result_path):
                with open(result_path, "r", encoding="utf-8") as file:
                    result: Dict[str, Any] = json.load(file)

                accuracy: float = float(result.get("accuracy", 0.0))
                print(
                    f"--- [INVOKER:{invoker_name}] Trial completed. Metric: {accuracy} ---"
                )
                return {
                    "status": "done",
                    "accuracy": accuracy,
                    "invoker": invoker_name,
                }

            raise FileNotFoundError(
                "Executor died but results.json not found in shared volume"
            )

        except docker.errors.ContainerError as exc:
            print(
                f"--- [INVOKER:{invoker_name}] Executor failed with exit code {exc.exit_status} ---"
            )
            raise RuntimeError(f"Executor failed: {exc}") from exc

        except Exception as exc:
            print(f"--- [INVOKER:{invoker_name}] Unexpected error: {exc} ---")
            raise exc

        finally:
            # Cleanup temporary trial directory
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                print(f"--- [INVOKER:{invoker_name}] Cleanup trial directory done ---")
