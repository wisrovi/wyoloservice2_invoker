"""Container execution dispatch and metric recovery logic for RunTraining step."""

import json
import os
import shutil
import tempfile
import time
from typing import Any

import yaml  # type: ignore # pylint: disable=import-error

from .env_loader import load_env_file
from .orchestrator import get_orchestrator
from .training_resources import apply_redis_dynamic_resources, parse_memory_to_bytes
from .training_timeouts import resolve_training_timeouts


def prepare_executor_environment(
    config: dict[str, Any], current_config: dict[str, Any], invoker_name: str
) -> tuple[dict[str, str], int, int, float]:
    """Prepare environment variables and calculate resource limits for executor container.

    Args:
        config (Dict[str, Any]): Invoker settings dictionary.
        current_config (Dict[str, Any]): Active trial training configuration.
        invoker_name (str): Identifier of invoker worker.

    Returns:
        Tuple[Dict[str, str], int, int, float]: Environment dict, shm bytes, mem bytes, cpu cores.
    """
    environments = os.environ.copy()
    environments.update(load_env_file("/app/config/control_host.env"))
    environments.update(load_env_file("/app/config/user.env"))

    environments.setdefault("CONTROL_HOST", "192.168.10.252")
    environments.setdefault("CIFS_USER", "wisrovi")
    environments.setdefault("CIFS_PASS", "wyoloservice")
    environments.setdefault("MAX_GPU", "30")
    environments.setdefault("WORKER_RAM_MEMORY", "6g")
    environments.setdefault("WORKER_CPU_CORES_AVAILABLE", "2.0")
    environments.setdefault("WORKER_SHM_MEMORY", "8g")

    apply_redis_dynamic_resources(environments, config, invoker_name)

    raw_device = (
        current_config.get("train", {}).get("device") if isinstance(current_config.get("train"), dict) else None
    )
    if raw_device is None:
        raw_device = current_config.get("device")
    target_gpu = (
        current_config.get("train", {}).get("gpu_id") if isinstance(current_config.get("train"), dict) else None
    )
    if target_gpu is None:
        target_gpu = raw_device if raw_device is not None else "0"
    environments["GPU_DEVICE_ID"] = str(target_gpu)

    shm_bytes = parse_memory_to_bytes(environments.get("WORKER_SHM_MEMORY", "8g"))
    mem_bytes = parse_memory_to_bytes(environments.get("WORKER_RAM_MEMORY", "6g"))
    try:
        cpu_cores = float(environments.get("WORKER_CPU_CORES_AVAILABLE", "2.0"))
    except ValueError:
        cpu_cores = 2.0

    return environments, shm_bytes, mem_bytes, cpu_cores


def execute_container_and_wait(
    config: dict[str, Any],
    image_name: str,
    executor_name: str,
    study_id: str | None,
    task_id: str | None,
    current_config: dict[str, Any],
    invoker_name: str,
) -> int:
    """Spawn executor container via orchestrator and block until completion.

    Args:
        config (Dict[str, Any]): Invoker settings dictionary.
        image_name (str): Docker image name.
        executor_name (str): Container name.
        study_id (Optional[str]): Optuna study ID.
        task_id (Optional[str]): Task ID.
        current_config (Dict[str, Any]): Active training configuration.
        invoker_name (str): Worker node name.

    Returns:
        int: Process exit code.
    """
    results_dir = config.get("results_dir", "/home/wyolo/train_service_results")
    environments, shm_bytes, mem_bytes, cpu_cores = prepare_executor_environment(config, current_config, invoker_name)
    timeout_info = resolve_training_timeouts(current_config, config)

    environments["STUDY_ID"] = str(study_id or "")
    environments["TASK_ID"] = str(task_id or "")
    environments["RESULTS_DIR"] = results_dir

    yaml_path = config.get("yaml_path", "/wyolo/worker/request/train.yaml")
    volumes = {
        results_dir: {"bind": "/wyolo/worker/train_service_results", "mode": "rw"},
        "/home/wyolo/events": {"bind": "/wyolo/worker/events", "mode": "rw"},
        "/home/wyolo/request": {"bind": "/wyolo/worker/request", "mode": "rw"},
    }
    orchestrator = get_orchestrator(config)
    default_cmd = (
        f"bash -c '(command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi || true) && "
        f'echo "[EXECUTOR] Starting mount..." && /usr/local/bin/mount-cifs.sh && '
        f'echo "[EXECUTOR] Mount OK. Starting training with developer-friendly background priority..." && '
        f"(nice -n 19 ionice -c 3 python main.py --file {yaml_path} 2>/dev/null || "
        f"nice -n 19 python main.py --file {yaml_path} || "
        f"python main.py --file {yaml_path})'"
    )
    cmd = config.get("command", default_cmd)

    return orchestrator.start_executor(
        image_name=image_name,
        executor_name=executor_name,
        environments=environments,
        volumes=volumes,
        command_str=cmd,
        shm_size_bytes=shm_bytes,
        mem_limit=mem_bytes,
        cpu_limit=cpu_cores,
        results_dir=results_dir,
        timeout_seconds=timeout_info["timeout_seconds"],
        invoker_name=invoker_name,
        redis_client=None,
    )
