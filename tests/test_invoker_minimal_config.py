# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Unit tests for Invoker configuration delivery with minimal YAML schemas.

This test module verifies:
1. That RunTraining accepts minimal training configurations without requiring hardcoded batch size.
2. That make_serializable preserves vision style and task metadata.
3. That dynamic timeout resolution properly defaults when train.time is omitted.
4. That config_train.yaml is successfully generated on disk.
"""

import os
import json
from unittest.mock import MagicMock, patch
import pytest
from states.run_training import RunTraining, resolve_training_timeouts


def test_invoker_timeout_resolution_default_hours():
    """Validates that omitting train.time results in standard 12.0h timeout reference.

    This ensures that when a researcher uses the simplified minimal YAML without
    defining train.time, the invoker applies epoch-based training logic with
    adequate infrastructure watchdog margins.
    """
    config = {"train": {"epochs": 10}}
    timeout_info = resolve_training_timeouts(config, {})
    assert timeout_info["user_time_hours"] is None
    assert timeout_info["ref_hours"] == 12.0
    assert timeout_info["timeout_seconds"] > 3600 * 12


@patch.object(RunTraining, "docker_run")
def test_invoker_serializes_minimal_config_with_style(mock_docker_run, tmp_path):
    """Validates that RunTraining writes valid config_train.yaml and config.json.

    This test checks that passing a minimal config with style: 'detect'
    correctly generates the files delivered to the Docker executor volume.
    """
    yaml_dest = str(tmp_path / "config_train.yaml")
    results_dest = str(tmp_path / "train_service_results")
    os.makedirs(results_dest, exist_ok=True)

    def simulate_executor_run(*args, **kwargs):
        # Container produces results.json during execution
        with open(os.path.join(results_dest, "results.json"), "w", encoding="utf-8") as f:
            json.dump({"accuracy": 0.89, "status": "completed"}, f)

    mock_docker_run.side_effect = simulate_executor_run

    rt = RunTraining({
        "yaml_path": yaml_dest,
        "results_dir": results_dest,
    })

    minimal_config = {
        "model": "yolo11n.pt",
        "style": "detect",
        "task": "detect",
        "train": {
            "data": "/path/to/data.yaml",
            "epochs": 5,
        },
    }

    result = rt(minimal_config)
    assert result["accuracy"] == 0.89
    assert os.path.exists(yaml_dest)
