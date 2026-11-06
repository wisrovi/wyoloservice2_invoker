"""Kubernetes Pod monitoring, wait polling, and deletion utilities."""

import time
from typing import Any, Dict
import requests
from .orchestrator_base import get_gpu_utilization
from .orchestrator_monitoring import check_cancellation_signal, write_telemetry_snapshot


def delete_k8s_pod_safely(base_url: str, namespace: str, pod_name: str, headers: Dict[str, str], ca_cert: Any) -> None:
    """Safely delete any pre-existing pod with the specified name.

    Args:
        base_url (str): Kubernetes API base URI.
        namespace (str): Target namespace.
        pod_name (str): Pod name to delete.
        headers (Dict[str, str]): HTTP authorization headers.
        ca_cert (Any): Cluster CA bundle path or False.
    """
    try:
        url = f"{base_url}/api/v1/namespaces/{namespace}/pods/{pod_name}?gracePeriodSeconds=0"
        requests.delete(url, headers=headers, verify=ca_cert, timeout=10)
    except Exception:
        pass


def wait_for_k8s_pod_completion(
    base_url: str,
    namespace: str,
    pod_name: str,
    executor_name: str,
    results_dir: str,
    timeout_seconds: int,
    environments: Dict[str, str],
    redis_client: Any,
    headers: Dict[str, str],
    ca_cert: Any,
) -> int:
    """Poll Kubernetes Pod phase until Succeeded, Failed, cancelled, or timed out.

    Args:
        base_url (str): Kubernetes API base URI.
        namespace (str): Namespace name.
        pod_name (str): Pod name.
        executor_name (str): Instance name.
        results_dir (str): Base output directory.
        timeout_seconds (int): Watchdog timeout.
        environments (Dict[str, str]): Environment variables.
        redis_client (Any): Connected Redis client.
        headers (Dict[str, str]): Request headers.
        ca_cert (Any): CA bundle path or False.

    Returns:
        int: Process exit code (0 for success).

    Raises:
        RuntimeError: If the pod execution times out.
    """
    url = f"{base_url}/api/v1/namespaces/{namespace}/pods/{pod_name}"
    task_id = environments.get("TASK_ID")
    study_id = environments.get("STUDY_ID")
    worker_ip = environments.get("WORKER_HOST")
    start = time.time()

    while time.time() - start < timeout_seconds:
        if check_cancellation_signal(redis_client, task_id, study_id, worker_ip):
            delete_k8s_pod_safely(base_url, namespace, pod_name, headers, ca_cert)
            return 130
        try:
            resp = requests.get(url, headers=headers, verify=ca_cert, timeout=5)
            if resp.status_code == 200:
                phase = resp.json().get("status", {}).get("phase", "Running")
                payload = {"status": phase.lower(), "gpu": get_gpu_utilization("0"), "timestamp": time.time()}
                write_telemetry_snapshot(results_dir, executor_name, payload, redis_client)
                if phase == "Succeeded":
                    delete_k8s_pod_safely(base_url, namespace, pod_name, headers, ca_cert)
                    return 0
                if phase == "Failed":
                    delete_k8s_pod_safely(base_url, namespace, pod_name, headers, ca_cert)
                    return 1
        except Exception:
            pass
        time.sleep(3)

    delete_k8s_pod_safely(base_url, namespace, pod_name, headers, ca_cert)
    raise RuntimeError(f"Pod execution timed out after {timeout_seconds} seconds")
