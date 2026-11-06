"""Resource limits resolution and memory parsing utilities for worker executor."""

import os
from typing import Any, Dict
import redis


def parse_memory_to_bytes(mem_str: str) -> int:
    """Convert human-readable memory string (e.g. '8g', '512m') into bytes.

    Args:
        mem_str (str): Memory string with unit suffix.

    Returns:
        int: Value in bytes.
    """
    mem_str = str(mem_str).strip().lower()
    units = {
        "b": 1,
        "k": 1024,
        "kb": 1024,
        "m": 1024**2,
        "mb": 1024**2,
        "g": 1024**3,
        "gb": 1024**3,
    }
    for unit, factor in sorted(units.items(), key=lambda x: -len(x[0])):
        if mem_str.endswith(unit):
            try:
                num = float(mem_str[: -len(unit)])
                return int(num * factor)
            except ValueError:
                pass
    try:
        return int(float(mem_str))
    except ValueError:
        return 6 * (1024**3)


def apply_redis_dynamic_resources(
    environments: Dict[str, str], config: Dict[str, Any], invoker_name: str
) -> None:
    """Fetch and apply host resource limits from Redis broker if registered.

    Args:
        environments (Dict[str, str]): Target environment mapping mutated in-place.
        config (Dict[str, Any]): Invoker settings dictionary.
        invoker_name (str): Identifier of the executing worker invoker.
    """
    worker_ip = os.getenv("WORKER_HOST") or environments.get("WORKER_HOST")
    if not worker_ip:
        return

    try:
        redis_url = config.get("redis_url", os.getenv("REDIS_URL", "redis://localhost:23437/0"))
        if "CONTROL_HOST" in environments and "REDIS_PORT" in environments:
            redis_url = f"redis://{environments['CONTROL_HOST']}:{environments['REDIS_PORT']}/{environments.get('REDIS_DB', '0')}"
        r_cli = redis.from_url(redis_url, socket_timeout=3)
        res_hash = r_cli.hgetall(f"invoker:{worker_ip}:resources")
        if not res_hash:
            return

        decoded = {
            (k.decode("utf-8") if isinstance(k, bytes) else str(k)): (
                v.decode("utf-8") if isinstance(v, bytes) else str(v)
            )
            for k, v in res_hash.items()
        }
        if decoded.get("max_gpu_percent"):
            raw_gpu = decoded["max_gpu_percent"]
            try:
                environments["MAX_GPU"] = str(int(float(raw_gpu)))
            except (ValueError, TypeError):
                environments["MAX_GPU"] = str(raw_gpu)
        if decoded.get("max_ram"):
            environments["WORKER_RAM_MEMORY"] = decoded["max_ram"]
        if decoded.get("max_cpu_cores"):
            environments["WORKER_CPU_CORES_AVAILABLE"] = decoded["max_cpu_cores"]
        if decoded.get("shm_size_gb"):
            raw_shm = decoded["shm_size_gb"]
            environments["WORKER_SHM_MEMORY"] = (
                f"{raw_shm}g" if not str(raw_shm).endswith(("g", "m", "k", "b")) else str(raw_shm)
            )
        print(
            f"--- [INVOKER:{invoker_name}] Applied dynamic resources from Redis: "
            f"MAX_GPU={environments.get('MAX_GPU')}%, RAM={environments.get('WORKER_RAM_MEMORY')}, "
            f"CPU={environments.get('WORKER_CPU_CORES_AVAILABLE')}, "
            f"SHM={environments.get('WORKER_SHM_MEMORY')} ---"
        )
    except Exception as exc:
        print(f"--- [INVOKER:{invoker_name}] Warning: Could not fetch limits from Redis: {exc} ---")
