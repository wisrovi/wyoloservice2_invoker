"""Unit tests for RunTraining state step."""

import json
import os
import shutil
import sys
import tempfile
import time
from unittest.mock import MagicMock, patch

if "optuna" not in sys.modules:
    sys.modules["optuna"] = MagicMock()

import pytest
from states.run_training import RunTraining


def mock_create_results_file(temp_results_dir: str) -> None:
    """Simulate executor writing completed results on finish."""
    results_path = os.path.join(temp_results_dir, "results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({"accuracy": 0.95, "status": "completed"}, f)


def mock_write_stale_file(temp_results_dir: str) -> None:
    """Simulate executor writing or reviving a file with an old modification time."""
    results_path = os.path.join(temp_results_dir, "results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({"accuracy": 0.50}, f)
    past_time = time.time() - 60.0
    os.utime(results_path, (past_time, past_time))


def mock_write_provisional_file(temp_results_dir: str) -> None:
    """Simulate executor writing provisional metrics during initialization."""
    results_path = os.path.join(temp_results_dir, "results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({"accuracy": 0.0, "status": "provisional"}, f)


class TestRunTraining:
    """Unit tests for the RunTraining class."""

    @pytest.fixture
    def temp_results_dir(self):
        """Create a temporary directory for results."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

    @pytest.fixture
    def config(self, temp_results_dir):
        """Provide a basic configuration for RunTraining."""
        return {
            "executor_image": "test_image:latest",
            "results_dir": temp_results_dir,
            "yaml_path": os.path.join(temp_results_dir, "config_train.yaml"),
        }

    @pytest.fixture
    def training_config(self):
        """Provide a basic training configuration."""
        return {"lr": 0.01, "epochs": 10}

    @patch.object(RunTraining, "docker_run")
    def test_call_success(self, mock_docker_run, config, training_config, temp_results_dir):
        """Validate a successful training trial execution."""
        mock_docker_run.side_effect = lambda *a, **kw: mock_create_results_file(temp_results_dir)
        run_training = RunTraining(config)
        result = run_training(training_config)

        assert result["status"] == "done"
        assert result["accuracy"] == 0.95
        assert mock_docker_run.called

    @patch.object(RunTraining, "docker_run")
    def test_call_results_not_found(self, mock_docker_run, config, training_config):
        """Validate that a FileNotFoundError is raised if results.json is missing."""
        run_training = RunTraining(config)
        with pytest.raises(FileNotFoundError, match="Executor finished but 'results.json' was not found"):
            run_training(training_config)

    @patch.object(RunTraining, "docker_run")
    def test_call_stale_results_rejected(self, mock_docker_run, config, training_config, temp_results_dir):
        """Validate that a stale results.json from previous executions is rejected."""
        mock_docker_run.side_effect = lambda *a, **kw: mock_write_stale_file(temp_results_dir)
        run_training = RunTraining(config)
        with pytest.raises(RuntimeError, match="Stale results.json detected"):
            run_training(training_config)

    @patch.object(RunTraining, "docker_run")
    def test_call_provisional_status_rejected(self, mock_docker_run, config, training_config, temp_results_dir):
        """Validate that provisional or failed status results are rejected."""
        mock_docker_run.side_effect = lambda *a, **kw: mock_write_provisional_file(temp_results_dir)
        run_training = RunTraining(config)
        with pytest.raises(RuntimeError, match="Executor produced non-completed status"):
            run_training(training_config)
