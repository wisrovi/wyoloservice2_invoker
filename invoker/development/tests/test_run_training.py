import pytest
from unittest.mock import MagicMock, patch
import os
import json
import shutil
import tempfile
from worker.invoker.states.run_training import RunTraining


class TestRunTraining:
    """
    Unit tests for the RunTraining class.

    This class validates the training execution flow, including configuration delivery,
    container execution, and results recovery.
    """

    @pytest.fixture
    def config(self):
        """Provides a basic configuration for RunTraining."""
        return {"executor_image": "test_image:latest"}

    @pytest.fixture
    def training_config(self):
        """Provides a basic training configuration."""
        return {"lr": 0.01, "epochs": 10}

    @patch("worker.invoker.states.run_training.docker.from_env")
    @patch("worker.invoker.states.run_training.tempfile.mkdtemp")
    def test_call_success(self, mock_mkdtemp, mock_docker, config, training_config):
        """
        Validates a successful training execution.

        Steps:
        1. Mocks the temporary directory and docker client.
        2. Simulates the creation of results.json by the executor.
        3. Checks if the returned accuracy matches the one in results.json.
        """
        # Setup temp dir mock
        temp_dir = tempfile.mkdtemp()
        mock_mkdtemp.return_value = temp_dir

        # Mock docker client and run
        mock_client = MagicMock()
        mock_docker.return_value = mock_client

        # Instantiate and call
        run_training = RunTraining(config)

        # Simulate results.json creation before it's read
        results_path = os.path.join(temp_dir, "results.json")
        with open(results_path, "w") as f:
            json.dump({"accuracy": 0.95}, f)

        result = run_training(training_config)

        assert result["status"] == "done"
        assert result["accuracy"] == 0.95
        assert mock_client.containers.run.called

        # Cleanup
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

    @patch("worker.invoker.states.run_training.docker.from_env")
    def test_call_results_not_found(self, mock_docker, config, training_config):
        """
        Validates that a FileNotFoundError is raised if results.json is missing.
        """
        mock_client = MagicMock()
        mock_docker.return_value = mock_client

        run_training = RunTraining(config)

        with pytest.raises(FileNotFoundError, match="results.json not found"):
            run_training(training_config)
