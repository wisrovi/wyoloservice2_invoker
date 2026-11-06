"""Docker container execution monitoring and log streaming."""

import os
import threading
import time
from typing import Any, Dict, List
from .orchestrator_base import get_gpu_utilization
from .orchestrator_monitoring import check_cancellation_signal, extract_current_epoch, write_telemetry_snapshot


def monitor_docker_container_loop(
    container: Any,
    executor_name: str,
    results_dir: str,
    environments: Dict[str, str],
    selected_gpus: List[str],
    redis_client: Any,
    stop_event: threading.Event,
    cancelled_flag: List[bool],
) -> None:
    """Run polling loop for Docker container stats, GPU usage, and cancellation.

    Args:
        container (Any): Docker container instance.
        executor_name (str): Instance name.
        results_dir (str): Base output directory.
        environments (Dict[str, str]): Environment variables.
        selected_gpus (List[str]): Active GPU device index list.
        redis_client (Any): Connected Redis client.
        stop_event (threading.Event): Thread termination signal.
        cancelled_flag (List[bool]): Mutable boolean container for cancellation state.
    """
    task_id = environments.get("TASK_ID") or environments.get("CELERY_TASK_ID")
    study_id = environments.get("STUDY_ID")
    worker_ip = environments.get("WORKER_HOST") or os.getenv("WORKER_HOST")

    while not stop_event.is_set():
        if check_cancellation_signal(redis_client, task_id, study_id, worker_ip):
            cancelled_flag[0] = True
            try:
                container.kill()
            except Exception:
                pass
            break
        try:
            container.reload()
            stats = container.stats(stream=False)
            primary_gpu = selected_gpus[0] if selected_gpus and selected_gpus[0] != "all" else "0"
            payload = {
                "status": "cancelled" if cancelled_flag[0] else "running",
                "gpu": get_gpu_utilization(primary_gpu),
                "epoch": extract_current_epoch(container.logs(tail=50).decode("utf-8", errors="ignore")),
                "timestamp": time.time(),
            }
            write_telemetry_snapshot(results_dir, executor_name, payload, redis_client)
        except Exception:
            pass
        time.sleep(2)


def stream_docker_logs_to_file(container: Any, executor_name: str, log_file_path: str) -> None:
    """Stream container standard output and standard error to local log file.

    Args:
        container (Any): Docker container instance.
        executor_name (str): Container name.
        log_file_path (str): Target output file path.
    """
    if not log_file_path:
        return
    try:
        with open(log_file_path, "w", encoding="utf-8") as lf:
            for line in container.logs(stream=True, follow=True):
                txt = line.decode("utf-8", errors="replace").rstrip()
                if txt:
                    print(f"[{executor_name}] {txt}", flush=True)
                    lf.write(txt + "\n")
                    lf.flush()
    except Exception:
        pass


def run_monitored_docker_container(
    container: Any,
    executor_name: str,
    results_dir: str,
    timeout_seconds: int,
    environments: Dict[str, str],
    selected_gpus: List[str],
    redis_client: Any,
) -> int:
    """Execute container monitoring and wait for process exit code.

    Args:
        container (Any): Docker container object.
        executor_name (str): Container name.
        results_dir (str): Host directory for telemetry.
        timeout_seconds (int): Watchdog timeout.
        environments (Dict[str, str]): Environment mapping.
        selected_gpus (List[str]): Active GPU indices.
        redis_client (Any): Connected Redis client.

    Returns:
        int: Container process exit code.

    Raises:
        RuntimeError: If the container fails or times out.
    """
    log_file_path = os.path.join(results_dir, f"executor_{executor_name}.log") if results_dir else ""
    stop_event = threading.Event()
    cancelled_flag = [False]

    mon_t = threading.Thread(
        target=monitor_docker_container_loop,
        args=(container, executor_name, results_dir, environments, selected_gpus, redis_client, stop_event, cancelled_flag),
        daemon=True,
    )
    log_t = threading.Thread(
        target=stream_docker_logs_to_file,
        args=(container, executor_name, log_file_path),
        daemon=True,
    )
    mon_t.start()
    log_t.start()

    try:
        wait_res = container.wait(timeout=timeout_seconds)
        exit_code = int(wait_res.get("StatusCode", 0))
    except Exception as exc:
        container.stop(timeout=10)
        container.remove(force=True)
        raise RuntimeError(f"Executor failed or timed out: {exc}")
    finally:
        stop_event.set()
        mon_t.join(timeout=2)
        log_t.join(timeout=3)

    container.remove(force=True)
    return 130 if cancelled_flag[0] else exit_code
