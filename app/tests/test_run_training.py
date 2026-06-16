import json
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from states.run_training import RunTraining


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
        return {"executor_image": "test_image:latest", "results_dir": temp_results_dir}

    @pytest.fixture
    def training_config(self):
        """Provides a basic training configuration."""
        return {"lr": 0.01, "epochs": 10}

    @patch("states.run_training.docker.from_env")
    def test_call_success(self, mock_docker, config, training_config, temp_results_dir):
        """Validates a successful training execution.

        Steps:
        1. Mocks the docker client.
        2. Simulates the creation of results.json by the executor.
        3. Checks if the returned accuracy matches the one in results.json.
        """
        # Mock docker client and run
        mock_client = MagicMock()
        mock_docker.return_value = mock_client
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.return_value = [b"log line 1", b"log line 2"]

        # Instantiate and call
        run_training = RunTraining(config)

        # Simulate results.json creation before it's read
        results_path = os.path.join(temp_results_dir, "results.json")
        with open(results_path, "w") as f:
            json.dump({"accuracy": 0.95}, f)

        result = run_training(training_config)

        assert result["status"] == "done"
        assert result["accuracy"] == 0.95
        assert mock_client.containers.run.called

    @patch("states.run_training.docker.from_env")
    def test_call_results_not_found(self, mock_docker, config, training_config):
        """Validates that a FileNotFoundError is raised if results.json is missing."""
        mock_client = MagicMock()
        mock_docker.return_value = mock_client
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.return_value = [b"log line 1"]

        run_training = RunTraining(config)

        with pytest.raises(FileNotFoundError, match="results.json not found"):
            run_training(training_config)
