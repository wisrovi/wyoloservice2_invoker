"""Hybrid execution orchestrator factory and facade for worker invoker."""

from typing import Any, Dict, Optional

from .docker_orchestrator import DockerOrchestrator
from .k8s_orchestrator import KubernetesOrchestrator
from .orchestrator_base import (
    BaseOrchestrator,
    get_gpu_utilization,
    get_optimal_gpu_device,
    is_k8s_environment,
    sanitize_k8s_name,
)

__all__ = [
    "BaseOrchestrator",
    "DockerOrchestrator",
    "KubernetesOrchestrator",
    "get_gpu_utilization",
    "get_optimal_gpu_device",
    "get_orchestrator",
    "is_k8s_environment",
    "sanitize_k8s_name",
]


def get_orchestrator(config: dict[str, Any] | None = None) -> BaseOrchestrator:
    """Instantiate and return the appropriate orchestrator for current environment.

    Args:
        config (Optional[Dict[str, Any]]): Invoker configuration dictionary.

    Returns:
        BaseOrchestrator: DockerOrchestrator or KubernetesOrchestrator instance.
    """
    if is_k8s_environment():
        print("--- [INVOKER] Detected Kubernetes environment. Using KubernetesOrchestrator. ---")
        return KubernetesOrchestrator(config)
    print("--- [INVOKER] Detected Docker environment. Using DockerOrchestrator. ---")
    return DockerOrchestrator(config)
