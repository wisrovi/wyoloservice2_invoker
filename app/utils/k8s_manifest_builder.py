"""Kubernetes Pod specification and manifest builder utilities."""

from typing import Any, Dict


def build_k8s_pod_manifest(
    pod_name: str,
    namespace: str,
    node_name: str,
    image_name: str,
    command_str: str,
    environments: Dict[str, str],
    volumes: Dict[str, Any],
    shm_gb: int,
    mem_gb: int,
    cpu_limit: float,
    timeout_seconds: int,
    trial_id: str,
    gpu_str: str,
) -> Dict[str, Any]:
    """Generate a validated Kubernetes Pod specification manifest.

    Args:
        pod_name (str): DNS-1123 label for the Pod.
        namespace (str): Target namespace.
        node_name (str): Pinned node name.
        image_name (str): Docker container image.
        command_str (str): Bash command string.
        environments (Dict[str, str]): Runtime environment variables.
        volumes (Dict[str, Any]): Mounted host directories.
        shm_gb (int): Shared memory size in gigabytes.
        mem_gb (int): Memory limit in gigabytes.
        cpu_limit (float): Max CPU limit.
        timeout_seconds (int): Active deadline in seconds.
        trial_id (str): Trial identifier.
        gpu_str (str): GPU count string.

    Returns:
        Dict[str, Any]: Complete Kubernetes Pod definition dictionary.
    """
    env_list = [{"name": str(k), "value": str(v)} for k, v in environments.items()]
    pod_volumes: list[Dict[str, Any]] = [
        {"name": "dshm", "emptyDir": {"medium": "Memory", "sizeLimit": f"{shm_gb}Gi"}}
    ]
    volume_mounts: list[Dict[str, Any]] = [{"name": "dshm", "mountPath": "/dev/shm"}]

    vol_idx = 0
    for host_path, mount_cfg in volumes.items():
        v_name = f"vol-{vol_idx}"
        vol_idx += 1
        m_path = mount_cfg.get("bind", host_path) if isinstance(mount_cfg, dict) else host_path
        pod_volumes.append({"name": v_name, "hostPath": {"path": host_path, "type": "DirectoryOrCreate"}})
        volume_mounts.append({"name": v_name, "mountPath": m_path})

    limits: Dict[str, Any] = {"memory": f"{mem_gb}Gi"}
    if cpu_limit > 0:
        limits["cpu"] = str(cpu_limit)
    if gpu_str != "0":
        limits["nvidia.com/gpu"] = gpu_str

    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": pod_name,
            "namespace": namespace,
            "labels": {"app": "wyolo-executor", "node": node_name, "trial_id": str(trial_id)},
        },
        "spec": {
            "nodeName": node_name,
            "restartPolicy": "Never",
            "activeDeadlineSeconds": max(1, int(timeout_seconds)),
            "tolerations": [
                {"key": "nvidia.com/gpu", "operator": "Exists", "effect": "NoSchedule"},
                {"key": "node.kubernetes.io/disk-pressure", "operator": "Exists"},
            ],
            "containers": [
                {
                    "name": "executor",
                    "image": image_name,
                    "imagePullPolicy": "IfNotPresent",
                    "command": ["/bin/bash", "-c", command_str],
                    "env": env_list,
                    "volumeMounts": volume_mounts,
                    "securityContext": {"privileged": True},
                    "resources": {"limits": limits, "requests": {"memory": "2Gi", "cpu": "1000m"}},
                }
            ],
            "volumes": pod_volumes,
        },
    }
