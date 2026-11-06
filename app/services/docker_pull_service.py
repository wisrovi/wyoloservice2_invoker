"""Docker image pull service for cluster broadcast updates."""

import os
from typing import Any, Dict


def execute_force_docker_pull(image_name: str) -> Dict[str, Any]:
    """Force local pull of specified Docker container image on this worker host.

    Args:
        image_name (str): Target container image tag.

    Returns:
        Dict[str, Any]: Pull operation summary including status and worker node.
    """
    import docker  # type: ignore

    worker_ip = os.getenv("WORKER_HOST", "unknown")
    node_name = os.getenv("WORKER_NAME", worker_ip)
    print(f"--- [PULL BROADCAST] Worker {node_name} ({worker_ip}) pulling image: {image_name} ---")

    try:
        client = docker.from_env()
        pull_stream = client.api.pull(image_name, stream=True, decode=True)
        for line in pull_stream:
            status = line.get("status", "")
            progress = line.get("progress", "")
            if status in ("Downloading", "Extracting") and progress:
                pass
            elif status:
                print(f"[{node_name}] {status}", flush=True)

        return {"status": "success", "worker": node_name, "ip": worker_ip, "image": image_name}
    except Exception as exc:
        err_msg = str(exc)
        print(f"❌ [PULL BROADCAST ERROR] Failed on {node_name}: {err_msg}", flush=True)
        return {"status": "error", "worker": node_name, "ip": worker_ip, "image": image_name, "error": err_msg}
