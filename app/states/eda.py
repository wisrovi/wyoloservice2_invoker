# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Exploratory Data Analysis (EDA) State Module.

This module provides the EDA class for performing initial data analysis before training.
"""

import os
import json
from typing import Any, Dict


class EDA:
    """State class for performing Exploratory Data Analysis."""

    NAME: str = "EDA"
    VERSION: str = "1.0.0"

    def __init__(self, config: dict[str, Any]):
        """Initialize EDA with configuration.

        Args:
            config: Worker configuration dictionary.
        """
        self.config = config

    def __call__(self, training_config: dict[str, Any]) -> dict[str, Any]:
        """Execute EDA process via temporary Executor container.

        Args:
            training_config: Training configuration.

        Returns:
            Dict[str, Any]: Results of the EDA.
        """
        print(f"--- [STATE:{self.NAME}] Running EDA via temporary Executor container... ---")
        dataset_path = training_config.get("train", {}).get("data")

        if not dataset_path:
            print("EDA skipped: dataset path not found")
            return {
                "status": "success",
                "eda_results": {},
            }

        # Run the temporary executor container to perform the mount and run python
        try:
            import docker
            client = docker.from_env()

            executor_image = self.config.get(
                "executor_image",
                "wisrovi/train_service:worker_executor_v1.0.0"
            )
            executor_name = f"wyolo_eda_runner_{os.getenv('PRIVATE_QUEUE', 'default')}"

            # Remove existing container just in case
            try:
                existing = client.containers.get(executor_name)
                existing.remove(force=True)
            except Exception:
                pass

            environments = {
                "CONTROL_HOST": os.getenv("CONTROL_HOST", "127.0.0.1"),
                "CIFS_USER": os.getenv("CIFS_USER", "wisrovi"),
                "CIFS_PASS": os.getenv("CIFS_PASS", "wyoloservice"),
            }

            print(f"[EDA] Spawning temp container {executor_name} with image {executor_image}...")
            container_output = client.containers.run(
                image=executor_image,
                name=executor_name,
                detach=False,
                privileged=True,
                network_mode="host",
                environment=environments,
                volumes={
                    "/home/wyolo/events": {
                        "bind": "/wyolo/worker/events",
                        "mode": "rw",
                    },
                    "/home/wyolo/train_service_results": {
                        "bind": "/wyolo/worker/train_service_results",
                        "mode": "rw",
                    },
                    "/home/wyolo/request": {
                        "bind": "/wyolo/worker/request",
                        "mode": "rw",
                    },
                },
                command=[
                    "bash",
                    "-c",
                    (
                        f"/usr/local/bin/mount-cifs.sh && "
                        f"python -c \"import sys; sys.path.append('/app'); "
                        f"from states.utils.dataset_analyzer import DatasetAnalyzer; "
                        f"import json; print(json.dumps(DatasetAnalyzer().analyze('{dataset_path}')))\""
                    )
                ],
                remove=True
            )

            output_str = container_output.decode("utf-8", errors="ignore")
            print(f"[EDA] Container output logs:\n{output_str}")

            json_start = output_str.find('{"dataset_type":')
            if json_start == -1:
                json_start = output_str.find('{"success":')

            if json_start == -1:
                raise ValueError("Could not find JSON output in container logs.")
            
            json_str = output_str[json_start:]
            json_end = json_str.rfind('}')
            if json_end != -1:
                json_str = json_str[:json_end+1]

            data = json.loads(json_str)
            # If the output is a wrapped run_eda response or direct analysis dict
            if "success" in data and not data.get("success"):
                raise RuntimeError(data.get("error", "Unknown error in container execution"))
            
            eda_results = data.get("results", data) if "results" in data else data
            return {
                "status": "success",
                "eda_results": eda_results,
            }

        except Exception as exc:
            print(f"EDA failed: {exc}")
            return {
                "status": "success",
                "eda_results": {},
                "eda_error": str(exc),
            }
