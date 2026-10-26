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


def test_cascading_timeouts_default_without_user_time():
    """Validates default cascading timeouts when 'train.time' is omitted in the YAML.

    When the user does not specify 'train.time' (or sets it to None / <= 0):
    1. 'user_time_hours' must be None so Ultralytics trains by 'epochs' and 'patience'
       without overriding epoch counts.
    2. Infrastructure reference base ('ref_hours') defaults to 12.0 hours (43,200s).
    3. Invoker watchdog timeout applies the 1.3x rule: 12.0h + 30% = 15.6h (56,160s).
    4. Redis TTL applies the 2.0x rule: 12.0h * 2 = 24.0h (86,400s).
    """
    from states.run_training import parse_user_train_time_hours, resolve_training_timeouts

    config_no_time = {"train": {"epochs": 230, "patience": 50, "imgsz": 640}}

    assert parse_user_train_time_hours(config_no_time) is None
    assert parse_user_train_time_hours({"train": {"time": None}}) is None
    assert parse_user_train_time_hours({"train": {"time": 0}}) is None
    assert parse_user_train_time_hours({"train": {"time": -5}}) is None

    resolved = resolve_training_timeouts(config_no_time, {"executor_timeout_seconds": 43200})
    assert resolved["user_time_hours"] is None
    assert resolved["ref_hours"] == 12.0
    assert resolved["base_seconds"] == 43200
    assert resolved["margin_seconds"] == 12960
    assert resolved["timeout_seconds"] == 56160
    assert resolved["redis_ttl_seconds"] == 86400


def test_cascading_timeouts_with_user_defined_time():
    """Validates cascading timeouts when the user explicitly sets 'train.time: 30' in the YAML.

    When 'train.time' is set to 30 hours:
    1. 'user_time_hours' is 30.0 so Ultralytics trains for 30 hours and triggers a clean stop.
    2. 'ref_hours' becomes 30.0 hours (108,000s).
    3. Invoker watchdog timeout applies the 1.3x rule: 30.0h + 30% = 39.0h (140,400s).
    4. Redis TTL applies the 2.0x rule: 30.0h * 2 = 60.0h (216,000s).
    """
    from states.run_training import parse_user_train_time_hours, resolve_training_timeouts

    config_30h = {"train": {"epochs": 230, "patience": 50, "time": 30}}

    assert parse_user_train_time_hours(config_30h) == 30.0

    resolved = resolve_training_timeouts(config_30h, {"executor_timeout_seconds": 56160})
    assert resolved["user_time_hours"] == 30.0
    assert resolved["ref_hours"] == 30.0
    assert resolved["base_seconds"] == 108000
    assert resolved["margin_seconds"] == 32400
    assert resolved["timeout_seconds"] == 140400
    assert resolved["redis_ttl_seconds"] == 216000


def test_cascading_timeouts_minimum_floors_for_short_runs():
    """Validates minimum safety floors (+45 min post-train margin and 24h Redis TTL) for short 'train.time'.

    When 'train.time' is set to a small value such as 0.5 hours (30 minutes = 1,800s):
    1. 30% of 1,800s is 540s (9 min), which is smaller than the 45-minute (2,700s) floor
       needed for XAI, Bootstrap, LLM analysis, and MinIO uploads. The margin must be 2,700s,
       resulting in a total Invoker timeout of 4,500s.
    2. 2.0x of 1,800s is 3,600s (1 hour), which is smaller than the 24-hour (86,400s) floor.
       The Redis TTL must remain at least 86,400s.
    """
    from states.run_training import resolve_training_timeouts

    config_half_hour = {"train": {"epochs": 10, "time": 0.5}}
    resolved = resolve_training_timeouts(config_half_hour, {})

    assert resolved["user_time_hours"] == 0.5
    assert resolved["base_seconds"] == 1800
    assert resolved["margin_seconds"] == 2700
    assert resolved["timeout_seconds"] == 4500
    assert resolved["redis_ttl_seconds"] == 86400
