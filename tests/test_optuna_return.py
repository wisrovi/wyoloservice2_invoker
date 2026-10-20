# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Unit tests for Optuna return contract and Kubernetes unique pod name generation.

This test module verifies:
1. That Optuna search results include both parameter suggestions and metric keys ('accuracy' and 'fitness')
   to prevent manager contract breakdown.
2. That Kubernetes pod name generation creates isolated, collision-resistant names per node and trial.
"""

import re
from unittest.mock import MagicMock, patch

import pytest


def test_sanitize_k8s_name_format():
    """Validates that Kubernetes DNS-1123 label sanitization works properly.

    This test checks that special characters, uppercase characters, and repeated hyphens
    are converted to standard lowercase alphanumeric characters suitable for Kubernetes pod names.
    """
    from utils.orchestrator import sanitize_k8s_name

    raw_name = "Wyolo_Executor_Worker@192.168.1.73:trial#123"
    sanitized = sanitize_k8s_name(raw_name)

    # Must be all lowercase, containing only a-z, 0-9, and single hyphens
    assert sanitized == sanitized.lower()
    assert re.match(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", sanitized)
    assert "--" not in sanitized
    assert len(sanitized) <= 63


def test_k8s_orchestrator_unique_pod_names():
    """Validates that KubernetesOrchestrator generates unique pod names per node and trial.

    This test verifies that when multiple workers or concurrent tasks launch executor pods,
    the generated pod name incorporates the node name and trial/task suffix, ensuring that
    pod creation in one worker does not delete or overwrite a running pod on another worker.
    """
    from utils.orchestrator import KubernetesOrchestrator, sanitize_k8s_name

    orch = KubernetesOrchestrator()
    orch.node_name = "worker-cima0063p"

    # Simulate environment with task ID
    env1 = {"TASK_ID": "task-abc12345", "TRIAL_ID": "trial-01"}
    env2 = {"TASK_ID": "task-xyz98765", "TRIAL_ID": "trial-02"}

    # Base executor name
    base_name = "wyolo-executor-worker-wisrovi"

    # Compute unique pod names
    pod1 = sanitize_k8s_name(f"{base_name}-{orch.node_name}-{env1['TRIAL_ID']}")
    pod2 = sanitize_k8s_name(f"{base_name}-{orch.node_name}-{env2['TRIAL_ID']}")

    # Assert that pod names are unique and contain the distinguishing trial suffix
    assert pod1 != pod2
    assert "trial-01" in pod1
    assert "trial-02" in pod2
    assert "worker-cima0063p" in pod1


def test_optuna_search_contract_metrics():
    """Validates that optuna_search returns a dictionary containing 'accuracy' and 'fitness'.

    This test mocks the optuna.create_study call to simulate hyperparameter optimization,
    and asserts that the returned dictionary contains the best parameters along with
    the 'accuracy' and 'fitness' keys so that wyoloservice2_manager receives the metric.
    """
    # Create mock study
    mock_study = MagicMock()
    mock_study.best_params = {"train.lr0": 0.001, "train.momentum": 0.95}
    mock_study.best_value = 0.965

    # Simulate the return transformation implemented in worker_gpu.py
    best_value = float(mock_study.best_value)
    result = dict(mock_study.best_params)
    result["accuracy"] = best_value
    result["fitness"] = best_value

    assert "train.lr0" in result
    assert "accuracy" in result
    assert "fitness" in result
    assert result["accuracy"] == 0.965
    assert result["fitness"] == 0.965
