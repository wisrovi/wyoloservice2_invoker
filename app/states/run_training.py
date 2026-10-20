# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Run Training State Module.

This module defines the RunTraining class, which orchestrates the execution
of training trials within Docker containers. It handles configuration delivery,
container management, and results recovery.
"""

import json
import multiprocessing
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from typing import Any, Dict, Tuple

import docker  # pylint: disable=import-error
import redis
import yaml
from requests.exceptions import ConnectionError, ReadTimeout
from rich.console import Console
from rich.table import Table

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


def get_system_limits(config: dict[str, Any], environments: dict[str, str]) -> tuple[float, int]:
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
    VERSION: str = "1.0.5"

    def __init__(self, config: dict[str, Any]):
        """Initializes the RunTraining instance.

        Args:
            config (Dict[str, Any]): Configuration dictionary containing executor settings.
        """
        self.config = config
        # Container-internal path for the training config YAML. Overridable via
        # config["yaml_path"] so tests running on the host can inject a writable
        # temp path instead of the container mount (/wyolo/worker/request).
        self.yaml_path: str = self.config.get("yaml_path", YAML_PATH)
        print(f"Executor timeout configured: {self.config.get('executor_timeout_seconds', 43200)}")

    def docker_run(
        self,
        image_name: str,
        executor_name: str,
        _temp_dir: str,
        study_id: str | None = None,
        task_id: str | None = None,
    ) -> None:
        """Runs a Docker container with the specified configuration.

        Args:
            image_name (str): The name of the Docker image to run.
            executor_name (str): The name to assign to the running container.
            _temp_dir (str): The local directory to bind as a volume (unused for now).
            study_id (str): Optional Optuna study identifier.
            task_id (str): Optional task identifier.
        """
        results_dir = self.config.get("results_dir", "/home/wyolo/train_service_results")
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
                    print(f"--- [INVOKER] Warning: Error reading env file {path}: {e} ---")
            return envs

        # Environment priority: Files > os.environ > Defaults
        environments = os.environ.copy()
        # In the invoker container, these are usually at /app/config/
        environments.update(load_env_file("/app/config/control_host.env"))
        environments.update(load_env_file("/app/config/user.env"))

        # Fallback cluster defaults to prevent localhost CIFS mount failures
        environments.setdefault("CONTROL_HOST", "192.168.10.252")
        environments.setdefault("CIFS_USER", "wisrovi")
        environments.setdefault("CIFS_PASS", "wyoloservice")

        # Check dynamic limits from Redis hash invoker:<worker_ip>:resources
        worker_ip = os.getenv("WORKER_HOST") or environments.get("WORKER_HOST")
        if worker_ip:
            try:
                redis_url = self.config.get("redis_url", os.getenv("REDIS_URL", "redis://localhost:23437/0"))
                if "CONTROL_HOST" in environments and "REDIS_PORT" in environments:
                    redis_url = f"redis://{environments['CONTROL_HOST']}:{environments['REDIS_PORT']}/{environments.get('REDIS_DB', '0')}"
                r_cli = redis.from_url(redis_url, socket_timeout=3)
                res_hash = r_cli.hgetall(f"invoker:{worker_ip}:resources")
                if res_hash:
                    decoded_res = {
                        k.decode("utf-8") if isinstance(k, bytes) else str(k): v.decode("utf-8")
                        if isinstance(v, bytes)
                        else str(v)
                        for k, v in res_hash.items()
                    }
                    if decoded_res.get("max_gpu_percent"):
                        raw_gpu = decoded_res["max_gpu_percent"]
                        try:
                            environments["MAX_GPU"] = str(int(float(raw_gpu)))
                        except (ValueError, TypeError):
                            environments["MAX_GPU"] = str(raw_gpu)
                    if decoded_res.get("max_ram"):
                        environments["WORKER_RAM_MEMORY"] = decoded_res["max_ram"]
                    if decoded_res.get("max_cpu_cores"):
                        environments["WORKER_CPU_CORES_AVAILABLE"] = decoded_res["max_cpu_cores"]
                    print(
                        f"--- [INVOKER:{invoker_name}] Applied dynamic resources from Redis: "
                        f"MAX_GPU={environments.get('MAX_GPU')}%, RAM={environments.get('WORKER_RAM_MEMORY')}, "
                        f"CPU={environments.get('WORKER_CPU_CORES_AVAILABLE')} ---"
                    )
            except Exception as r_err:
                print(f"--- [INVOKER:{invoker_name}] Warning: Could not fetch dynamic limits from Redis: {r_err} ---")

        environments.update(
            {
                "NVIDIA_VISIBLE_DEVICES": "0",
                "NVIDIA_DRIVER_CAPABILITIES": "all",
                "TZ": "Europe/Madrid",
                "PYTHONUNBUFFERED": "1",
                "TASK_ID": str(task_id or ""),
                "STUDY_ID": str(study_id or ""),
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
            console = Console()
            res_table = Table(
                show_header=True,
                header_style="bold magenta",
                title="\n[bold]Recursos Asignados (Límites Docker - Vista Invoker)[/bold]",
            )
            res_table.add_column("Recurso", style="dim")
            res_table.add_column("Asignación", justify="right")

            max_gpu_env = environments.get("MAX_GPU", "-1")
            gpu_asignada = f"{max_gpu_env}%" if max_gpu_env != "-1" else "Sin límite (100%)"
            res_table.add_row("Uso máximo VRAM (Autobatch)", gpu_asignada)

            limit_ram = environments.get("WORKER_RAM_MEMORY", "Desconocido")
            res_table.add_row("RAM Total Disponible", limit_ram)

            limit_cpu = environments.get("WORKER_CPU_CORES", "Desconocido")
            res_table.add_row("CPU Cores (Afinidad)", limit_cpu)

            limit_shm = environments.get("WORKER_SHM_MEMORY") or environments.get("WORKER_RAM_MEMORY", "Desconocido")
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

            samba_table.add_row("control_server_HOST", environments.get("CONTROL_HOST", "Desconocido"))
            samba_table.add_row("USER", environments.get("CIFS_USER", "Desconocido"))
            samba_table.add_row("PASS", environments.get("CIFS_PASS", "Desconocido"))

            console.print(samba_table)
        except ImportError:
            print("--- [INVOKER] Please install 'rich' to see the resources table nicely formatted. ---")

        try:
            # Clean up stale results before running
            results_dir = self.config.get("results_dir", "/home/wyolo/train_service_results")
            stale_result_path: str = os.path.join(results_dir, "results.json")
            if os.path.exists(stale_result_path):
                os.remove(stale_result_path)
                print("--- [INVOKER] Stale results.json removed. ---")

            # Clean up stale telemetry before running
            if os.path.exists(telemetry_file):
                os.remove(telemetry_file)
            try:
                from utils.orchestrator import get_orchestrator
            except ImportError:
                import sys

                if "/app" not in sys.path:
                    sys.path.insert(0, "/app")
                from utils.orchestrator import get_orchestrator

            # Calculate shm_size: minimum 16g (17179869184 bytes), or use mem_limit if mem_limit > 16g
            min_shm_bytes = 16 * 1024**3
            shm_size_bytes = max(min_shm_bytes, mem_limit)

            volumes = {
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
            }

            command_str = (
                f'bash -c \'nvidia-smi && echo "[EXECUTOR] Starting mount..." && '
                f'/usr/local/bin/mount-cifs.sh && echo "[EXECUTOR] Mount OK. Starting training..." && '
                f"python main.py --file {self.yaml_path}'"
            )

            redis_client = None
            try:
                redis_client = redis.from_url(self.config.get("redis_url", "redis://localhost:23437/0"))
            except Exception as e:
                print(f"[INVOKER] Warning: Could not connect to redis for stats: {e}")

            orchestrator = get_orchestrator(self.config)
            exit_code = orchestrator.start_executor(
                image_name=image_name,
                executor_name=executor_name,
                environments=environments,
                volumes=volumes,
                command_str=command_str,
                shm_size_bytes=shm_size_bytes,
                mem_limit=mem_limit,
                cpu_limit=cpu_limit,
                results_dir=results_dir,
                timeout_seconds=timeout_seconds,
                invoker_name=invoker_name,
                redis_client=redis_client,
            )

            if exit_code != 0:
                print(f"--- [INVOKER:{invoker_name}] Executor failed with exit code {exit_code} ---")
                raise RuntimeError(f"Executor failed with exit code {exit_code}.")

        except Exception as exc:
            private_queue = os.getenv("WORKER_NAME", "unknown")
            print(f"--- [INVOKER:{private_queue}] Error in docker_run: {exc} ---")

            # Mark MLflow run as FAILED if MLFLOW_RUN_ID is available
            mlflow_run_id = environments.get("MLFLOW_RUN_ID")
            mlflow_tracking_uri = environments.get("MLFLOW_TRACKING_URI", os.getenv("MLFLOW_TRACKING_URI"))
            if mlflow_run_id and mlflow_tracking_uri:
                try:
                    import requests

                    requests.post(
                        f"{mlflow_tracking_uri.rstrip('/')}/api/2.0/mlflow/runs/update",
                        json={
                            "run_id": mlflow_run_id,
                            "status": "FAILED",
                            "end_time": int(time.time() * 1000),
                        },
                        timeout=5,
                    )
                    print(f"--- [INVOKER] Marked MLflow run {mlflow_run_id} as FAILED ---")
                except Exception as ml_err:
                    print(f"--- [INVOKER] Warning: Failed to update MLflow run to FAILED: {ml_err} ---")

            # put -1 in results.json to indicate failure for Optuna
            results_dir = self.config.get("results_dir", "/home/wyolo/train_service_results")
            os.makedirs(results_dir, exist_ok=True)

            final_result_path: str = os.path.join(results_dir, "results.json")

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
                return {k: make_serializable(v) for k, v in data.items() if not k.startswith("_")}
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

        if clean_config.get("dry_run") is True or clean_config.get("sweeper", {}).get("dry_run") is True:
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
            os.makedirs(os.path.dirname(self.yaml_path), exist_ok=True)

            with open(self.yaml_path, "w", encoding="utf-8") as file:
                yaml.dump(clean_config, file)

            config_path: str = os.path.join(temp_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as file:
                json.dump(clean_config, file, indent=4)

            # Ensure stale results.json is purged before launching trial
            results_dir = self.config.get("results_dir", "/home/wyolo/train_service_results")
            stale_results_file = os.path.join(results_dir, "results.json")
            if os.path.exists(stale_results_file):
                try:
                    os.remove(stale_results_file)
                    print(f"--- [INVOKER:{invoker_name}] Purged pre-existing results.json ---")
                except OSError as os_err:
                    print(
                        f"--- [INVOKER:{invoker_name}] Warning: Could not purge pre-existing results.json: {os_err} ---"
                    )

            trial_start_time = time.time()

            # 2. Run the EXECUTOR
            # name_for_logs = f"wyolo_executor_{invoker_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            name_for_logs = f"wyolo_executor_{invoker_name}"
            study_id = training_config.get("study_id")
            task_id = training_config.get("task_id") or clean_config.get("task_id")
            self.docker_run(
                image_name=self.config.get("executor_image", DEFAULT_TRAIN_IMAGE),
                executor_name=name_for_logs,
                _temp_dir=temp_dir,
                study_id=study_id,
                task_id=task_id,
            )

            # 3. Recover Metric: Optuna needs the accuracy to proceed
            # The executor writes results to /wyolo/worker/train_service_results/results.json
            result_file_path: str = os.path.join(results_dir, "results.json")
            if os.path.exists(result_file_path):
                file_mtime = os.path.getmtime(result_file_path)
                if file_mtime < trial_start_time - 2.0:
                    raise RuntimeError(
                        f"Stale results.json detected (mtime: {file_mtime} < start: {trial_start_time}). "
                        f"Rejecting leftover results from previous executions."
                    )

                with open(result_file_path, encoding="utf-8") as file:
                    result: dict[str, Any] = json.load(file)

                # Check for explicit failure or provisional status
                res_status = str(result.get("status", "")).lower()
                if res_status in ("failed", "error", "provisional"):
                    raise RuntimeError(f"Executor produced non-completed status in results.json: {result}")

                accuracy: float = float(result.get("accuracy", 0.0))
                print(f"--- [INVOKER:{invoker_name}] Trial completed. Metric: {accuracy} ---")
                evaluation_dir = os.path.join(results_dir, "evaluation_metrics")
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
