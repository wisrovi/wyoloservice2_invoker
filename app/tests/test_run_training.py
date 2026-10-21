# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Docstring."""

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
from worker_gpu import check_gpu_health


class TestRunTraining:
    """Unit tests for the RunTraining class.

    This class validates the training execution flow, including configuration delivery,
    container execution, and results recovery.
    """

    @pytest.fixture
    def temp_results_dir(self):
        """Creates a temporary directory for results."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

    @pytest.fixture
    def config(self, temp_results_dir):
        """Provides a basic configuration for RunTraining."""
        return {
            "executor_image": "test_image:latest",
            "results_dir": temp_results_dir,
            "yaml_path": os.path.join(temp_results_dir, "config_train.yaml"),
        }

    @pytest.fixture
    def training_config(self):
        """Provides a basic training configuration."""
        return {"lr": 0.01, "epochs": 10}

    @patch.object(RunTraining, "docker_run")
    def test_call_success(self, mock_docker_run, config, training_config, temp_results_dir):
        """Validates a successful training trial execution.

        This test verifies that:
        1. The RunTraining class correctly delegates container execution to docker_run.
        2. When the executor successfully writes a results.json file, the class recovers
           and returns the metrics (accuracy) and status correctly.

        To achieve this cleanly, we mock the `docker_run` method. In the mocked method's
        side effect, we simulate the container writing the `results.json` output file to
        the shared results directory. This prevents the real `docker_run` from executing and
        deleting the file we set up before it runs.
        """

        # Set up side effect to create results.json inside the temp results dir
        # simulating the docker executor writing the results on completion
        def create_results_file(*args, **kwargs):
            """Simulate executor writing completed results on finish."""
            results_path = os.path.join(temp_results_dir, "results.json")
            with open(results_path, "w", encoding="utf-8") as f:
                json.dump({"accuracy": 0.95, "status": "completed"}, f)

        mock_docker_run.side_effect = create_results_file

        # Instantiate RunTraining and execute it
        run_training = RunTraining(config)
        result = run_training(training_config)

        # Assertions
        assert result["status"] == "done"
        assert result["accuracy"] == 0.95
        assert mock_docker_run.called

    @patch.object(RunTraining, "docker_run")
    def test_call_results_not_found(self, mock_docker_run, config, training_config):
        """Validates that a FileNotFoundError is raised if results.json is missing.

        This test verifies that if the executor fails to write results.json (for example, if
        it crashes or is misconfigured), the RunTraining class detects the missing file
        and raises a FileNotFoundError with a descriptive error message.

        By mocking `docker_run` to do nothing, we simulate an execution that exits without
        producing the results.json file in the shared directory.
        """
        run_training = RunTraining(config)

        # Execute and assert that FileNotFoundError is raised with the expected error message
        with pytest.raises(
            FileNotFoundError,
            match="Executor finished but 'results.json' was not found in the shared volume",
        ):
            run_training(training_config)

    @patch.object(RunTraining, "docker_run")
    def test_call_stale_results_rejected(self, mock_docker_run, config, training_config, temp_results_dir):
        """Validates that a stale results.json from previous executions is rejected."""

        def write_stale_file(*args, **kwargs):
            """Simulate executor writing or reviving a file with an old modification time."""
            results_path = os.path.join(temp_results_dir, "results.json")
            with open(results_path, "w", encoding="utf-8") as f:
                json.dump({"accuracy": 0.50}, f)
            past_time = time.time() - 60.0
            os.utime(results_path, (past_time, past_time))

        mock_docker_run.side_effect = write_stale_file

        run_training = RunTraining(config)
        with pytest.raises(RuntimeError, match="Stale results.json detected"):
            run_training(training_config)

    @patch.object(RunTraining, "docker_run")
    def test_call_provisional_status_rejected(self, mock_docker_run, config, training_config, temp_results_dir):
        """Validates that provisional or failed status results are rejected."""

        def write_provisional_file(*args, **kwargs):
            """Simulate executor writing provisional metrics during initialization."""
            results_path = os.path.join(temp_results_dir, "results.json")
            with open(results_path, "w", encoding="utf-8") as f:
                json.dump({"accuracy": 0.0, "status": "provisional"}, f)

        mock_docker_run.side_effect = write_provisional_file

        run_training = RunTraining(config)
        with pytest.raises(RuntimeError, match="Executor produced non-completed status"):
            run_training(training_config)

    @patch("utils.orchestrator.get_orchestrator")
    def test_call_user_cancellation_recorded(self, mock_get_orch, config, training_config, temp_results_dir):
        """Validates that user cancellation writes status 'cancelled' into results.json."""
        mock_orch = MagicMock()
        mock_orch.start_executor.side_effect = RuntimeError("Executor wyolo_executor was cancelled by user request.")
        mock_get_orch.return_value = mock_orch

        run_training = RunTraining(config)
        with pytest.raises(RuntimeError, match="cancelled by user request"):
            run_training(training_config)

        results_path = os.path.join(temp_results_dir, "results.json")
        assert os.path.exists(results_path)
        with open(results_path, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
        assert saved_data["status"] == "cancelled"
        assert saved_data["accuracy"] == -1.0

    @patch("subprocess.run")
    def test_check_gpu_health_success(self, mock_sub):
        """Validates check_gpu_health returning healthy status on valid nvidia-smi output."""
        mock_res = MagicMock()
        mock_res.stdout = "NVIDIA GeForce RTX 3060, 550.54, 45\n"
        mock_res.returncode = 0
        mock_sub.return_value = mock_res

        is_healthy, msg = check_gpu_health()
        assert is_healthy is True
        assert "RTX 3060" in msg

    @patch("subprocess.run")
    def test_check_gpu_health_failure(self, mock_sub):
        """Validates check_gpu_health returning unhealthy status when nvidia-smi fails."""
        import subprocess

        mock_sub.side_effect = subprocess.CalledProcessError(1, ["nvidia-smi"], stderr="Driver error")

        is_healthy, msg = check_gpu_health()
        assert is_healthy is False
        assert "Driver error" in msg
