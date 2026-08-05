"""Run Training State Module.

This module defines the RunTraining class, which orchestrates the execution
of training trials within Docker containers. It handles configuration delivery,
container management, and results recovery.
"""

from rich.console import Console
from rich.table import Table
import json
import multiprocessing
import os
import shutil
import tempfile
import time
import subprocess
import re
from datetime import datetime
from typing import Any, Dict, Tuple
import threading

import redis


from requests.exceptions import ReadTimeout, ConnectionError

import docker  # pylint: disable=import-error
import yaml

DEFAULT_TRAIN_IMAGE = "wisrovi/train_service:worker_executor_v1.0.0"
BASE_DIR = "/wyolo/worker/request"
FILE = "config_train.yaml"
YAML_PATH = os.path.join(BASE_DIR, FILE)


def parse_memory_to_bytes(mem_str: str) -> int:
    """Parses a memory limit string (e.g., '28g', '512m') to bytes."""
    mem_str = mem_str.strip().lower()
    if not mem_str:
        raise ValueError("Empty memory string")

    # Extract numeric part and unit
    units = {"b": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}

    # Find where the unit starts (if any)
    num_chars = []
    unit_char = "b"
    for char in mem_str:
        if char.isdigit() or char == ".":
            num_chars.append(char)
        elif char in units:
            unit_char = char
            break

    num_val = float("".join(num_chars))
    return int(num_val * units[unit_char])


def get_system_limits(
    config: dict[str, Any], environments: dict[str, str]
) -> tuple[float, int]:
    """Calculates the hardware limits based on the host system and config.

    Args:
        config (Dict[str, Any]): The worker configuration dictionary.
        environments (Dict[str, str]): Loaded environment variables.

    Returns:
        tuple: (cpu_limit, mem_limit_bytes)
    """
    cpu_pct = float(config.get("cpu_limit_pct", 0.85))
    mem_pct = float(config.get("mem_limit_pct", 0.60))

    # 1. CPU: Priority: WORKER_CPU_CORES_AVAILABLE > WORKER_CPU_CORES > Percentage of total cores
    cores_env = (
        environments.get("WORKER_CPU_CORES_AVAILABLE")
        or environments.get("WORKER_CPU_CORES")
        or os.getenv("WORKER_CPU_CORES_AVAILABLE")
        or os.getenv("WORKER_CPU_CORES")
    )
    if cores_env:
        try:
            cpu_limit = float(cores_env)
        except ValueError:
            total_cpus = multiprocessing.cpu_count()
            cpu_limit = float(total_cpus * cpu_pct)
    else:
        total_cpus = multiprocessing.cpu_count()
        cpu_limit = float(total_cpus * cpu_pct)

    # 2. RAM: Priority: WORKER_RAM_MEMORY > Percentage of total host memory
    ram_env = environments.get("WORKER_RAM_MEMORY") or os.getenv("WORKER_RAM_MEMORY")
    if ram_env:
        try:
            mem_limit_bytes = parse_memory_to_bytes(ram_env)
        except Exception:
            total_mem_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
            mem_limit_bytes = int(total_mem_bytes * mem_pct)
    else:
        total_mem_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        mem_limit_bytes = int(total_mem_bytes * mem_pct)

    return cpu_limit, mem_limit_bytes


def get_gpu_usage() -> float:
    """Get current GPU utilization percentage from the executor container."""
    try:
        result = subprocess.check_output(
            [
                "docker",
                "exec",
                "wyolo_executor",
                "nvidia-smi",
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return float(result.strip().split("\n")[0])
    except Exception:
        return 0.0


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
    VERSION: str = "1.0.1"

    def __init__(self, config: dict[str, Any]):
        """Initializes the RunTraining instance.

        Args:
            config (Dict[str, Any]): Configuration dictionary containing executor settings.
        """
        self.config = config
        print(
            f"Executor timeout configured: "
            f"{self.config.get('executor_timeout_seconds', 43200)}"
        )

    def docker_run(self, image_name: str, executor_name: str, _temp_dir: str, study_id: str | None = None) -> None:
        """Runs a Docker container with the specified configuration.

        Args:
            image_name (str): The name of the Docker image to run.
            executor_name (str): The name to assign to the running container.
            _temp_dir (str): The local directory to bind as a volume (unused for now).
            study_id (str): Optional Optuna study identifier.
        """
        results_dir = self.config.get(
            "results_dir", "/home/wyolo/train_service_results"
        )
        telemetry_file = os.path.join(results_dir, "telemetry.json")

        invoker_name = os.getenv("WORKER_NAME", os.getenv("PRIVATE_QUEUE", "unknown"))
        timeout_seconds = self.config.get(
            "executor_timeout_seconds",
            43200,
        )

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
                    print(
                        f"--- [INVOKER] Warning: Error reading env file {path}: {e} ---"
                    )
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

        # Calculate hardware limits dynamically from config and environment variables
        cpu_limit, mem_limit = get_system_limits(self.config, environments)

        print(
            f"--- [INVOKER:{invoker_name}] Launching executor: {executor_name} with limits "
            f"(CPU: {cpu_limit:.2f}, RAM: {mem_limit // (1024**2)}MB) ---"
            f"Executor timeout: {timeout_seconds}s ---"
        )

        try:
            client = docker.from_env()
        except Exception as exc:
            worker_name = os.getenv("WORKER_NAME", "unknown")
            print(f"--- [INVOKER:{worker_name}] Unexpected error: {exc} ---")
            raise exc

        try:

            console = Console()
            res_table = Table(
                show_header=True,
                header_style="bold magenta",
                title="\n[bold]Recursos Asignados (Límites Docker - Vista Invoker)[/bold]",
            )
            res_table.add_column("Recurso", style="dim")
            res_table.add_column("Asignación", justify="right")

            max_gpu_env = environments.get("MAX_GPU", "-1")
            gpu_asignada = (
                f"{max_gpu_env}%" if max_gpu_env != "-1" else "Sin límite (100%)"
            )
            res_table.add_row("Uso máximo VRAM (Autobatch)", gpu_asignada)

            limit_ram = environments.get("WORKER_RAM_MEMORY", "Desconocido")
            res_table.add_row("RAM Total Disponible", limit_ram)

            limit_cpu = environments.get("WORKER_CPU_CORES", "Desconocido")
            res_table.add_row("CPU Cores (Afinidad)", limit_cpu)

            limit_shm = environments.get("WORKER_SHM_MEMORY") or environments.get(
                "WORKER_RAM_MEMORY", "Desconocido"
            )
            res_table.add_row("Memoria Compartida (SHM)", limit_shm)

            console.print(res_table)

            # Tabla de Samba
            samba_table = Table(
                show_header=False,
                border_style="cyan",
                title="\n[bold cyan]Credenciales Samba[/bold cyan]",
            )
            samba_table.add_column("Parámetro", style="bold")
            samba_table.add_column("Valor")

            samba_table.add_row(
                "control_server_HOST", environments.get("CONTROL_HOST", "Desconocido")
            )
            samba_table.add_row("USER", environments.get("CIFS_USER", "Desconocido"))
            samba_table.add_row("PASS", environments.get("CIFS_PASS", "Desconocido"))

            console.print(samba_table)
        except ImportError:
            print(
                "--- [INVOKER] Please install 'rich' to see the resources table nicely formatted. ---"
            )

        try:
            # Clean up stale results before running
            results_dir = self.config.get(
                "results_dir", "/home/wyolo/train_service_results"
            )
            stale_result_path: str = os.path.join(results_dir, "results.json")
            if os.path.exists(stale_result_path):
                os.remove(stale_result_path)
                print("--- [INVOKER] Stale results.json removed. ---")

            # Clean up stale telemetry before running
            if os.path.exists(telemetry_file):
                os.remove(telemetry_file)
                print("--- [INVOKER] Stale telemetry.json removed. ---")

            # Force remove any existing container with the same name to prevent conflict
            try:
                existing_container = client.containers.get(executor_name)
                print(
                    f"--- [INVOKER] Found existing container {executor_name}. Removing... ---"
                )
                existing_container.remove(force=True)
            except Exception:
                pass

            # Calculate shm_size: minimum 16g (17179869184 bytes), or use mem_limit if mem_limit > 16g
            min_shm_bytes = 16 * 1024**3
            shm_size_bytes = max(min_shm_bytes, mem_limit)

            container = client.containers.run(
                image=image_name,
                # pull="always",  # only for download the image from docker hub (obligatory for first time)
                name=executor_name,
                hostname=environments.get("USER", "default_user"),
                detach=True,
                remove=False,  # Don't remove yet so we can check status/logs if needed
                privileged=True,
                network_mode="host",
                shm_size=shm_size_bytes,
                tty=False,  # Disable TTY to avoid multiplexing issues and ANSI codes
                # Resource Limits
                nano_cpus=int(cpu_limit * 1e9),
                mem_limit=mem_limit,
                # Capabilities
                cap_add=["SYS_ADMIN", "DAC_READ_SEARCH", "NET_ADMIN", "SYS_RESOURCE"],
                # GPU Configuration
                device_requests=[
                    docker.types.DeviceRequest(device_ids=["0"], capabilities=[["gpu"]])
                ],
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

            print(
                f"--- [INVOKER] Executor {executor_name} started. Streaming logs... ---",
                flush=True,
            )

            # Start resource monitoring thread
            stop_monitor = False
            redis_client = redis.from_url(
                self.config.get("redis_url", "redis://localhost:23437/0")
            )

            def get_current_epoch(container) -> str:
                """Extract current training epoch from executor logs."""
                try:
                    logs = container.logs(tail=100).decode("utf-8", errors="ignore")
                    matches = re.findall(r"\s+(\d+)/\d+\s+\d+\.\d+G", logs)
                    if matches:
                        return matches[-1]
                except Exception as exc:
                    print(f"[MONITOR] Epoch extraction error: {exc}")
                return "N/A"

            def monitor_resources():
                while not stop_monitor:
                    try:
                        container.reload()
                        stats = container.stats(stream=False)
                        cpu_stats = stats.get("cpu_stats", {})
                        precpu_stats = stats.get("precpu_stats", {})

                        cpu_delta = (
                            cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
                            - precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
                        )
                        system_delta = (
                            cpu_stats.get("system_cpu_usage", 0)
                            - precpu_stats.get("system_cpu_usage", 0)
                        )

                        if system_delta > 0:
                            cpu_percent = round(
                                (cpu_delta / system_delta)
                                * len(cpu_stats.get("cpu_usage", {}).get("percpu_usage", [1]))
                                * 100,
                                2,
                            )
                        else:
                            cpu_percent = 0.0

                        memory_usage = stats["memory_stats"].get("usage", 0)
                        mem_mb = round(memory_usage / (1024 * 1024), 2)
                        gpu_percent = get_gpu_usage()
                        epoch = get_current_epoch(container)

                        telemetry = {
                            "status": "running",
                            "cpu": cpu_percent,
                            "ram_mb": mem_mb,
                            "gpu": gpu_percent,
                            "epoch": epoch,
                            "timestamp": time.time(),
                        }
                        print(
                            f"[REDIS MONITOR] Writing executor:{executor_name}:stats -> {telemetry}",
                            flush=True,
                        )

                        tmp_telemetry_file = telemetry_file + ".tmp"
                        with open(tmp_telemetry_file, "w", encoding="utf-8") as file:
                            json.dump(telemetry, file, indent=4)
                        os.replace(tmp_telemetry_file, telemetry_file)

                        print(
                            f"[MONITOR] CPU={cpu_percent}% RAM={mem_mb}MB GPU={gpu_percent}%",
                            flush=True,
                        )
                    except Exception as exc:
                        print(f"[MONITOR] Error: {exc}")
                    time.sleep(5)

            monitor_thread = threading.Thread(target=monitor_resources, daemon=True)
            monitor_thread.start()

            # Prepare log file path in the shared results volume
            results_dir = self.config.get(
                "results_dir", "/home/wyolo/train_service_results"
            )
            log_file_path = os.path.join(results_dir, f"logs_{executor_name}.txt")

            # Stream logs to the invoker's output and save to a file
            # Prepare log file path in the shared results volume
            results_dir = self.config.get(
                "results_dir", "/home/wyolo/train_service_results"
            )
            log_file_path = os.path.join(results_dir, f"logs_{executor_name}.txt")

            def stream_logs():
                """Stream executor logs while the container is running."""
                try:
                    with open(log_file_path, "w", encoding="utf-8") as log_file:
                        log_stream = container.logs(stream=True, follow=True)

                        for line in log_stream:
                            try:
                                decoded_line = line.decode(
                                    "utf-8", errors="replace"
                                ).rstrip()

                                if decoded_line:
                                    formatted_line = f"[{executor_name}] {decoded_line}"

                                    print(formatted_line, flush=True)

                                    log_file.write(decoded_line + "\n")
                                    log_file.flush()

                            except Exception as exc:
                                print(
                                    f"--- [INVOKER] "
                                    f"Error decoding log line: {exc} ---"
                                )

                except Exception as exc:
                    print(f"--- [INVOKER] Error streaming logs: {exc} ---")

            # Start log streaming in background
            log_thread = threading.Thread(target=stream_logs, daemon=True)
            log_thread.start()

            # Wait for container with timeout
            timeout_seconds = self.config.get(
                "executor_timeout_seconds",
                43200,
            )

            try:
                result = container.wait(timeout=timeout_seconds)

            except (ReadTimeout, ConnectionError):
                print(
                    f"--- [INVOKER:{invoker_name}] "
                    f"Executor timeout after {timeout_seconds}s ---"
                )

                container.stop(timeout=30)
                container.remove(force=True)

                raise RuntimeError(
                    f"Executor exceeded timeout of " f"{timeout_seconds} seconds"
                )

            finally:
                stop_monitor = True
                monitor_thread.join(timeout=2)
                log_thread.join(timeout=5)

            exit_code = result.get("StatusCode", 0)

            # If it failed, try to get the full logs even if stream finished
            if exit_code != 0:
                print(
                    f"--- [INVOKER:{invoker_name}] Executor failed with exit code {exit_code} ---"
                )
                # Attempt to get full logs for debugging
                full_logs = container.logs(stdout=True, stderr=True).decode(
                    "utf-8", errors="replace"
                )
                print(f"--- [INVOKER] Full executor logs: ---\n{full_logs}")

                # Cleanup manually since remove=False
                container.remove()
                raise RuntimeError(
                    f"Executor failed with exit code {exit_code}. Logs:\n{full_logs[-1000:]}"
                )

            # Cleanup manually since remove=False
            container.remove()

            # Cleanup telemetry after successful execution
            try:
                with open(telemetry_file, "w", encoding="utf-8") as file:
                    json.dump(
                        {
                            "status": "finished",
                            "cpu": 0,
                            "ram_mb": 0,
                            "gpu": 0.0,
                            "timestamp": time.time(),
                        },
                        file,
                        indent=4,
                    )
            except Exception as e:
                print(f"--- [INVOKER] Failed to write final telemetry: {e} ---")

        except Exception as exc:
            private_queue = os.getenv("WORKER_NAME", "unknown")
            print(f"--- [INVOKER:{private_queue}] Error in docker_run: {exc} ---")

            # put -1 in results.json to indicate failure for Optuna
            results_dir = self.config.get(
                "results_dir", "/home/wyolo/train_service_results"
            )
            os.makedirs(results_dir, exist_ok=True)

            final_result_path: str = os.path.join(results_dir, "results.json")

            # Write failure result only if it doesn't exist (to avoid overwriting partial success if any)
            if not os.path.exists(final_result_path):
                try:
                    with open(final_result_path, "w", encoding="utf-8") as file:
                        json.dump(
                            {"accuracy": -1.0, "status": "failed", "error": str(exc)},
                            file,
                            indent=4,
                        )
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
        invoker_name = os.getenv("WORKER_NAME", os.getenv("PRIVATE_QUEUE", "unknown"))

        # Make the training config 100% clean and serializable to avoid PyYAML/JSON pickling errors (like _thread.RLock)
        def make_serializable(data: Any) -> Any:
            if isinstance(data, dict):
                return {
                    k: make_serializable(v)
                    for k, v in data.items()
                    if not k.startswith("_")
                }
            elif isinstance(data, list):
                return [make_serializable(v) for v in data]
            elif isinstance(data, (str, int, float, bool, type(None))):
                return data
            elif hasattr(data, "model_dump"):
                return make_serializable(data.model_dump())
            elif hasattr(data, "dict"):
                return make_serializable(data.dict())
            else:
                return str(data)

        clean_config = make_serializable(training_config)

        if (
            clean_config.get("dry_run") is True
            or clean_config.get("sweeper", {}).get("dry_run") is True
        ):
            import time

            print(
                f"--- [INVOKER:{invoker_name}] DRY RUN MODE ENABLED. Simulating training... ---",
                flush=True,
            )
            time.sleep(2)
            return {
                "status": "done",
                "accuracy": 0.95,
                "invoker": invoker_name,
                "dry_run": True,
            }

        # B108: Hardcoded /tmp is acceptable for this environment.
        # B103: Permissive mask is needed for shared volume access between host and container.
        temp_dir: str = tempfile.mkdtemp(prefix="trial_", dir="/tmp")  # nosec
        os.chmod(temp_dir, 0o777)  # nosec

        try:
            # 1. Deliver Config: Write the JSON config to a file for the executor
            # training_config in yaml file
            os.makedirs(os.path.dirname(YAML_PATH), exist_ok=True)

            with open(YAML_PATH, "w", encoding="utf-8") as file:
                yaml.dump(clean_config, file)

            config_path: str = os.path.join(temp_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as file:
                json.dump(clean_config, file, indent=4)

            # 2. Run the EXECUTOR
            # name_for_logs = f"wyolo_executor_{invoker_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            name_for_logs = f"wyolo_executor_{invoker_name}"
            study_id = training_config.get("study_id")
            self.docker_run(
                image_name=self.config.get("executor_image", DEFAULT_TRAIN_IMAGE),
                executor_name=name_for_logs,
                _temp_dir=temp_dir,
                study_id=study_id,
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
                print(
                    f"--- [INVOKER:{invoker_name}] Trial completed. Metric: {accuracy} ---"
                )
                evaluation_dir = os.path.join(
                    self.config.get(
                        "results_dir",
                        "/home/wyolo/train_service_results"
                    ),
                    "evaluation_metrics"
                )
                return {
                    "status": "done",
                    "accuracy": accuracy,
                    "invoker": invoker_name,
                    "results_image": os.path.join(evaluation_dir, "results.png"),
                    "confusion_matrix_image": os.path.join(evaluation_dir, "confusion_matrix.png"),
                    "results_csv": os.path.join(evaluation_dir, "results.csv"),
                }

            raise FileNotFoundError(
                "Executor finished but 'results.json' was not found in the shared volume. "
                "This typically indicates that the executor aborted early due to a configuration error, "
                "such as an invalid dataset path. Check the configuration and executor logs."
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
