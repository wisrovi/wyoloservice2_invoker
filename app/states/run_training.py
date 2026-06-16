"""Run Training State Module.

This module defines the RunTraining class, which orchestrates the execution
of training trials within Docker containers. It handles configuration delivery,
container management, and results recovery.
"""

import json
import multiprocessing
import os
import shutil
import tempfile
from datetime import datetime
from typing import Any, Dict, Tuple

import docker  # pylint: disable=import-error
import yaml

DEFAULT_TRAIN_IMAGE = "wisrovi/train_service:worker_executor_v1.0.0"
BASE_DIR = "/wyolo/worker/request"
FILE = "config_train.yaml"
YAML_PATH = os.path.join(BASE_DIR, FILE)


def get_system_limits(config: dict[str, Any]) -> tuple[float, int]:
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

    def __init__(self, config: dict[str, Any]):
        """Initializes the RunTraining instance.

        Args:
            config (Dict[str, Any]): Configuration dictionary containing executor settings.
        """
        self.config = config

    def docker_run(self, image_name: str, executor_name: str, _temp_dir: str) -> None:
        """Runs a Docker container with the specified configuration.

        Args:
            image_name (str): The name of the Docker image to run.
            executor_name (str): The name to assign to the running container.
            _temp_dir (str): The local directory to bind as a volume (unused for now).
        """
        invoker_name = os.getenv("PRIVATE_QUEUE", "unknown")

        # Calculate hardware limits dynamically from config
        cpu_limit, mem_limit = get_system_limits(self.config)

        print(
            f"--- [INVOKER:{invoker_name}] Launching executor: {executor_name} with limits "
            f"(CPU: {cpu_limit:.2f}, RAM: {mem_limit // (1024**2)}MB) ---"
        )

        try:
            client = docker.from_env()
        except Exception as exc:
            worker_name = os.getenv("WORKER_NAME", "unknown")
            print(f"--- [INVOKER:{worker_name}] Unexpected error: {exc} ---")
            raise exc

        def load_env_file(path: str) -> dict[str, str]:
            envs = {}
            if os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#"):
                                key_val = line.split("=", 1)
                                if len(key_val) == 2:
                                    envs[key_val[0]] = key_val[1]
                except Exception as e:
                    print(f"--- [INVOKER] Warning: Error reading env file {path}: {e} ---")
            return envs

        # Environment priority: Files > os.environ > Defaults
        environments = os.environ.copy()
        # In the invoker container, these are usually at /app/config/
        environments.update(load_env_file("/app/config/control_host.env"))
        environments.update(load_env_file("/app/config/user.env"))

        environments.update(
            {
                "NVIDIA_VISIBLE_DEVICES": "0",
                "NVIDIA_DRIVER_CAPABILITIES": "all",
                "TZ": "Europe/Madrid",
                "PYTHONUNBUFFERED": "1",
            }
        )

        try:
            # Clean up stale results before running
            results_dir = self.config.get("results_dir", "/home/wyolo/train_service_results")
            stale_result_path: str = os.path.join(results_dir, "results.json")
            if os.path.exists(stale_result_path):
                os.remove(stale_result_path)
                print("--- [INVOKER] Stale results.json removed. ---")

            # Force remove any existing container with the same name to prevent conflict
            try:
                existing_container = client.containers.get(executor_name)
                print(f"--- [INVOKER] Found existing container {executor_name}. Removing... ---")
                existing_container.remove(force=True)
            except Exception:
                pass

            container = client.containers.run(
                image=image_name,
                name=executor_name,
                hostname=environments.get("USER", "default_user"),
                detach=True,
                remove=False,  # Don't remove yet so we can check status/logs if needed
                privileged=True,
                network_mode="host",
                shm_size="16g",
                tty=False,  # Disable TTY to avoid multiplexing issues and ANSI codes
                # Resource Limits
                nano_cpus=int(8 * 1e9),  # --cpus=8
                mem_limit="24g",
                # Capabilities
                cap_add=["SYS_ADMIN", "DAC_READ_SEARCH", "NET_ADMIN", "SYS_RESOURCE"],
                # GPU Configuration
                device_requests=[docker.types.DeviceRequest(device_ids=["0"], capabilities=[["gpu"]])],
                # Environment
                environment=environments,
                # Labels
                labels={
                    "autoheal": "true",
                    "com.centurylinklabs.watchtower.enable": "true",
                },
                # Volumes
                volumes={
                    "/home/wyolo/events": {
                        "bind": "/wyolo/worker/events",
                        "mode": "rw",
                    },
                    "/home/wyolo/train_service_results": {
                        "bind": "/wyolo/worker/train_service_results",
                        "mode": "rw",
                    },
                    "/home/wyolo/request": {
                        "bind": "/wyolo/worker/request",
                        "mode": "rw",
                    },
                },
                # Command: More verbose for debugging
                command=(
                    f'bash -c \'nvidia-smi && echo "[EXECUTOR] Starting mount..." && '
                    f'/usr/local/bin/mount-cifs.sh && echo "[EXECUTOR] Mount OK. Starting training..." && '
                    f"python main.py --file {YAML_PATH}'"
                ),
            )

            print(f"--- [INVOKER] Executor {executor_name} started. Streaming logs... ---", flush=True)

            # Prepare log file path in the shared results volume
            results_dir = self.config.get("results_dir", "/home/wyolo/train_service_results")
            log_file_path = os.path.join(results_dir, f"logs_{executor_name}.txt")

            # Stream logs to the invoker's output and save to a file
            with open(log_file_path, "w", encoding="utf-8") as log_file:
                # Use a generator to get clean lines from the stream
                log_stream = container.logs(stream=True, follow=True)
                for line in log_stream:
                    try:
                        decoded_line = line.decode("utf-8", errors="replace").rstrip()
                        if decoded_line:
                            formatted_line = f"[{executor_name}] {decoded_line}"
                            print(formatted_line, flush=True)
                            log_file.write(decoded_line + "\n")
                            log_file.flush()
                    except Exception as e:
                        print(f"--- [INVOKER] Warning: Error decoding log line: {e} ---")

            # Wait for container to exit and check status
            result = container.wait()
            exit_code = result.get("StatusCode", 0)

            # If it failed, try to get the full logs even if stream finished
            if exit_code != 0:
                print(f"--- [INVOKER:{invoker_name}] Executor failed with exit code {exit_code} ---")
                # Attempt to get full logs for debugging
                full_logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
                print(f"--- [INVOKER] Full executor logs: ---\n{full_logs}")

                # Cleanup manually since remove=False
                container.remove()
                raise RuntimeError(f"Executor failed with exit code {exit_code}. Logs:\n{full_logs[-1000:]}")

            # Cleanup manually since remove=False
            container.remove()

        except Exception as exc:
            private_queue = os.getenv("WORKER_NAME", "unknown")
            print(f"--- [INVOKER:{private_queue}] Error in docker_run: {exc} ---")

            # put -1 in results.json to indicate failure for Optuna
            results_dir = self.config.get("results_dir", "/home/wyolo/train_service_results")
            os.makedirs(results_dir, exist_ok=True)

            final_result_path: str = os.path.join(results_dir, "results.json")

            # Write failure result only if it doesn't exist (to avoid overwriting partial success if any)
            if not os.path.exists(final_result_path):
                try:
                    with open(final_result_path, "w", encoding="utf-8") as file:
                        json.dump({"accuracy": -1.0, "status": "failed", "error": str(exc)}, file, indent=4)
                except Exception as e:
                    print(f"--- [INVOKER] Failed to write results.json: {e} ---")

            raise exc

    def __call__(self, training_config: dict[str, Any]) -> dict[str, Any]:
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
        invoker_name = os.getenv("WORKER_NAME", "unknown")

        # B108: Hardcoded /tmp is acceptable for this environment.
        # B103: Permissive mask is needed for shared volume access between host and container.
        temp_dir: str = tempfile.mkdtemp(prefix="trial_", dir="/tmp")  # nosec
        os.chmod(temp_dir, 0o777)  # nosec

        try:
            # 1. Deliver Config: Write the JSON config to a file for the executor
            # training_config in yaml file
            os.makedirs(os.path.dirname(YAML_PATH), exist_ok=True)

            with open(YAML_PATH, "w", encoding="utf-8") as file:
                yaml.dump(training_config, file)

            config_path: str = os.path.join(temp_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as file:
                json.dump(training_config, file, indent=4)

            # 2. Run the EXECUTOR
            # name_for_logs = f"wyolo_executor_{invoker_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            name_for_logs = f"wyolo_executor_{invoker_name}"
            self.docker_run(
                image_name=self.config.get("executor_image", DEFAULT_TRAIN_IMAGE),
                executor_name=name_for_logs,
                _temp_dir=temp_dir,
            )

            # 3. Recover Metric: Optuna needs the accuracy to proceed
            # The executor writes results to /wyolo/worker/train_service_results/results.json
            # which is mapped to a path in the invoker (default: /results)
            results_dir = self.config.get("results_dir", "/results")
            result_file_path: str = os.path.join(results_dir, "results.json")
            if os.path.exists(result_file_path):
                with open(result_file_path, encoding="utf-8") as file:
                    result: dict[str, Any] = json.load(file)

                accuracy: float = float(result.get("accuracy", 0.0))
                print(f"--- [INVOKER:{invoker_name}] Trial completed. Metric: {accuracy} ---")
                return {
                    "status": "done",
                    "accuracy": accuracy,
                    "invoker": invoker_name,
                }

            raise FileNotFoundError("Executor died but results.json not found in shared volume")

        except docker.errors.ContainerError as exc:
            print(f"--- [INVOKER:{invoker_name}] Executor failed with exit code {exc.exit_status} ---")
            raise RuntimeError(f"Executor failed: {exc}") from exc

        except Exception as exc:
            print(f"--- [INVOKER:{invoker_name}] Unexpected error: {exc} ---")
            raise exc

        finally:
            # Cleanup temporary trial directory
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                print(f"--- [INVOKER:{invoker_name}] Cleanup trial directory done ---")
