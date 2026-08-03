# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Docstring."""

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
            results_path = os.path.join(temp_results_dir, "results.json")
            with open(results_path, "w", encoding="utf-8") as f:
                json.dump({"accuracy": 0.95}, f)

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
