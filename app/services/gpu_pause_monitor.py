"""GPU health checking and background node pause monitoring service."""

import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from typing import Any, Dict, Tuple
import redis


def check_gpu_health() -> Tuple[bool, str]:
    """Check GPU health and NVIDIA driver responsiveness via nvidia-smi.

    Returns:
        Tuple[bool, str]: A tuple of (is_healthy, status_message).
    """
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=gpu_name,driver_version,temperature.gpu", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        output = res.stdout.strip()
        if not output:
            return False, "nvidia-smi returned empty output"
        return True, output.splitlines()[0]
    except subprocess.CalledProcessError as err:
        return False, f"nvidia-smi returned exit code {err.returncode}: {err.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, "nvidia-smi timed out after 5 seconds"
    except FileNotFoundError:
        return True, "nvidia-smi not found (CPU or development mode)"
    except Exception as exc:
        return False, f"Unexpected GPU healthcheck error: {str(exc)}"


def pause_monitor_thread(
    app_inst: Any, node_name: str, private_queue_ip: str, config: Dict[str, Any], version: str
) -> None:
    """Monitor pause state, GPU health, disk space, and publish heartbeats to Redis.

    Args:
        app_inst (Any): Celery application instance.
        node_name (str): Celery worker node name.
        private_queue_ip (str): Host IP bound to private queue.
        config (Dict[str, Any]): Worker invoker configuration.
        version (str): Worker version string.
    """
    print(f"[PAUSE MONITOR] Starting monitor thread for node: {node_name} (IP: {private_queue_ip})")
    public_queues = ["gpus_high", "gpus_medium", "gpus_low", "wyolo_gpu_queue"]
    public_queues_active = True
    gpu_error_active = False

    results_dir = config.get("results_dir", "/home/wyolo/train_service_results")
    check_path = results_dir if os.path.exists(results_dir) else "/"

    while True:
        try:
            redis_client = redis.from_url(app_inst.conf.broker_url)
            state_key = f"invoker:{private_queue_ip}:pause_state"
            until_key = f"invoker:{private_queue_ip}:pause_until"
            res_key = f"invoker:{private_queue_ip}:resources"
            heartbeat_key = f"invoker:{private_queue_ip}:heartbeat"

            state_bytes = redis_client.get(state_key)
            state = state_bytes.decode("utf-8") if state_bytes else "active"
            now = time.time()

            if state == "paused_temporal":
                until_bytes = redis_client.get(until_key)
                if until_bytes:
                    pause_until = float(until_bytes.decode("utf-8"))
                    if now >= pause_until:
                        redis_client.set(state_key, "active")
                        redis_client.delete(until_key)
                        state = "active"
                else:
                    redis_client.set(state_key, "active")
                    state = "active"

            gpu_healthy, gpu_msg = check_gpu_health()
            if not gpu_healthy:
                if not gpu_error_active:
                    redis_client.hset(res_key, "status", "gpu_unhealthy")
                    redis_client.hset(res_key, "gpu_error", gpu_msg)
                    gpu_error_active = True
            elif gpu_error_active:
                redis_client.hset(res_key, "status", "online")
                redis_client.hdel(res_key, "gpu_error")
                gpu_error_active = False

            disk_critical = False
            try:
                du = shutil.disk_usage(check_path)
                free_gb = du.free / (1024**3)
                total_gb = du.total / (1024**3)
                free_pct = (du.free / du.total) * 100.0 if du.total > 0 else 0.0
                disk_warning = free_pct < 10.0 or free_gb < 5.0
                disk_critical = free_pct < 5.0 or free_gb < 2.0
                redis_client.hset(
                    res_key,
                    mapping={
                        "disk_free_gb": f"{free_gb:.1f}",
                        "disk_total_gb": f"{total_gb:.1f}",
                        "disk_free_pct": f"{free_pct:.1f}",
                        "disk_warning": "true" if disk_warning else "false",
                    },
                )
            except Exception:
                pass

            heartbeat_payload = {
                "hostname": node_name,
                "ip": private_queue_ip,
                "version": version,
                "status": "gpu_unhealthy" if not gpu_healthy else state,
                "timestamp": now,
            }
            redis_client.set(heartbeat_key, json.dumps(heartbeat_payload), ex=30)
            redis_client.set(f"invoker:{private_queue_ip}:celery_node_name", node_name, ex=86400 * 7)
            redis_client.hset(res_key, "last_seen", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            should_pause = state in ("paused_perpetual", "paused_temporal", "draining") or not gpu_healthy or disk_critical
            if should_pause and public_queues_active:
                for q in public_queues:
                    app_inst.control.cancel_consumer(q, destination=[node_name])
                public_queues_active = False
            elif not should_pause and not public_queues_active:
                for q in public_queues:
                    app_inst.control.add_consumer(q, destination=[node_name])
                public_queues_active = True
        except Exception as exc:
            print(f"[PAUSE MONITOR] Error in monitor loop: {exc}")
        time.sleep(10)
