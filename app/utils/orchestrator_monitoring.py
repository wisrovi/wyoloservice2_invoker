"""Process monitoring, cancellation check, and log streaming helpers."""

import json
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional
from .orchestrator_base import get_gpu_utilization


def check_cancellation_signal(
    redis_client: Any,
    task_id: Optional[str],
    study_id: Optional[str],
    worker_ip: Optional[str],
) -> bool:
    """Check Redis broker for cancellation keys targeting task, study, or host drain.

    Args:
        redis_client (Any): Connected Redis client instance.
        task_id (Optional[str]): Celery task identifier.
        study_id (Optional[str]): Optuna study identifier.
        worker_ip (Optional[str]): Host node IP address.

    Returns:
        bool: True if cancellation is requested, False otherwise.
    """
    if not redis_client:
        return False
    try:
        keys: List[str] = []
        if task_id:
            keys.extend([f"wyolo:task:{task_id}:cancel", f"task:{task_id}:cancel"])
        if study_id:
            keys.extend([f"study:{study_id}:cancel", f"wyolo:study:{study_id}:cancel", f"study:{study_id}:cancelled"])
        if worker_ip:
            keys.append(f"invoker:{worker_ip}:cancel_active")
            drain_val = redis_client.get(f"invoker:{worker_ip}:drain")
            if drain_val:
                try:
                    raw_str = drain_val.decode() if isinstance(drain_val, bytes) else str(drain_val)
                    drain_data = json.loads(raw_str)
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


def extract_current_epoch(logs: str) -> str:
    """Extract current training epoch from recent log output.

    Args:
        logs (str): Tail string of process logs.

    Returns:
        str: Current epoch indicator string (e.g. '15/50') or 'N/A'.
    """
    try:
        matches = re.findall(r"\s+(\d+/\d+)\s+\d+\.\d+G", logs)
        if matches:
            return matches[-1]
        raw_num = re.findall(r"\s+(\d+)/\d+\s+\d+\.\d+G", logs)
        if raw_num:
            return raw_num[-1]
    except Exception:
        pass
    return "N/A"


def write_telemetry_snapshot(
    results_dir: str, executor_name: str, payload: Dict[str, Any], redis_client: Any
) -> None:
    """Persist runtime stats to Redis and atomic telemetry file.

    Args:
        results_dir (str): Base output directory.
        executor_name (str): Instance name.
        payload (Dict[str, Any]): Telemetry snapshot.
        redis_client (Any): Optional Redis client.
    """
    if redis_client:
        try:
            redis_client.set(f"executor:{executor_name}:stats", json.dumps(payload), ex=30)
        except Exception:
            pass
    if results_dir:
        telemetry_file = os.path.join(results_dir, f"telemetry_{executor_name}.json")
        tmp_file = telemetry_file + ".tmp"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=4)
            os.replace(tmp_file, telemetry_file)
        except Exception:
            pass
