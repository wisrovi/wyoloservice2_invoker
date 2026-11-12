"""RunTraining State Step Module for Invoker WPipe Pipeline."""

import contextlib
import json
import os
import shutil
import tempfile
import time
from typing import Any, Optional, Union

import yaml
from dto.training_context import TrainingContext
from utils.executor_runner import execute_container_and_wait
from utils.serialization import make_serializable
from utils.training_resources import parse_memory_to_bytes
from utils.training_timeouts import parse_user_train_time_hours, resolve_training_timeouts

# Backward compatibility constants and re-exports
DEFAULT_TRAIN_IMAGE = "wisrovi/train_service:worker_executor_v2.2.27"
YAML_PATH = "/wyolo/worker/request/train.yaml"

__all__ = [
    "DEFAULT_TRAIN_IMAGE",
    "YAML_PATH",
    "RunTraining",
    "parse_memory_to_bytes",
    "parse_user_train_time_hours",
    "resolve_training_timeouts",
]


class RunTraining:
    """Orchestrates the execution of a training trial via the container executor.

    Attributes:
        NAME (str): Module identifier name.
        VERSION (str): Step component version.
        config (Dict[str, Any]): Worker invoker settings dictionary.
        yaml_path (str): Target filesystem path for trial configuration YAML.
    """

    NAME: str = "RunTraining"
    VERSION: str = "2.0.0"

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize RunTraining step with worker configuration.

        Args:
            config (Optional[Dict[str, Any]]): Invoker settings dictionary.
        """
        self.config: dict[str, Any] = config or {}
        self.yaml_path: str = self.config.get("yaml_path", YAML_PATH)
        self.current_training_config: dict[str, Any] = {}

    def docker_run(
        self,
        image_name: str,
        executor_name: str,
        _temp_dir: str,
        study_id: str | None = None,
        task_id: str | None = None,
    ) -> None:
        """Run training container using the resolved orchestrator.

        Args:
            image_name (str): Container image to run.
            executor_name (str): Container instance name.
            _temp_dir (str): Host scratch directory.
            study_id (Optional[str]): Optuna study identifier.
            task_id (Optional[str]): Celery task identifier.
        """
        invoker_name = os.getenv("WORKER_NAME", os.getenv("PRIVATE_QUEUE", "unknown"))
        t_cfg = vars(self).get("current_training_config", {}) or {}
        execute_container_and_wait(self.config, image_name, executor_name, study_id, task_id, t_cfg, invoker_name)

    def __call__(self, context: dict[str, Any] | TrainingContext) -> dict[str, Any]:
        """Execute training state step within WPipe pipeline.

        Args:
            context (Union[Dict[str, Any], TrainingContext]): Pipeline context or config dict.

        Returns:
            Dict[str, Any]: Execution result containing accuracy and metric paths.

        Raises:
            FileNotFoundError: If results.json is missing after execution.
            RuntimeError: If executor container aborts or returns error status.
        """
        invoker_name = os.getenv("WORKER_NAME", os.getenv("PRIVATE_QUEUE", "unknown"))
        raw_cfg = context.training_config if isinstance(context, TrainingContext) else context
        clean_config = make_serializable(raw_cfg)

        user_time_hours = parse_user_train_time_hours(clean_config)
        if user_time_hours is not None:
            clean_config.setdefault("train", {})["time"] = user_time_hours

        self.current_training_config = clean_config

        if clean_config.get("dry_run") is True or clean_config.get("sweeper", {}).get("dry_run") is True:
            print(f"--- [INVOKER:{invoker_name}] DRY RUN MODE ENABLED. Simulating training... ---")
            return {"status": "done", "accuracy": 0.95, "invoker": invoker_name, "dry_run": True}

        temp_dir = tempfile.mkdtemp(prefix="trial_")

        try:
            os.makedirs(os.path.dirname(self.yaml_path), exist_ok=True)
            with open(self.yaml_path, "w", encoding="utf-8") as yf:
                yaml.dump(clean_config, yf)

            with open(os.path.join(temp_dir, "config.json"), "w", encoding="utf-8") as jf:
                json.dump(clean_config, jf, indent=4)

            results_dir = self.config.get("results_dir", "/home/wyolo/train_service_results")
            stale_file = os.path.join(results_dir, "results.json")
            if os.path.exists(stale_file):
                with contextlib.suppress(OSError):
                    os.remove(stale_file)

            trial_start_time = time.time()
            executor_name = f"wyolo_executor_{invoker_name}"
            study_id = clean_config.get("study_id")
            task_id = clean_config.get("task_id")

            self.docker_run(
                image_name=self.config.get("executor_image", DEFAULT_TRAIN_IMAGE),
                executor_name=executor_name,
                _temp_dir=temp_dir,
                study_id=study_id,
                task_id=task_id,
            )

            result_file = os.path.join(results_dir, "results.json")
            if not os.path.exists(result_file):
                raise FileNotFoundError(f"Executor finished but 'results.json' was not found at {result_file}.")

            if os.path.getmtime(result_file) < trial_start_time - 2.0:
                raise RuntimeError("Stale results.json detected from a prior execution.")

            with open(result_file, encoding="utf-8") as rf:
                result_data = json.load(rf)

            if str(result_data.get("status", "")).lower() in ("failed", "error", "provisional"):
                raise RuntimeError(f"Executor produced non-completed status: {result_data}")

            acc = float(result_data.get("accuracy", 0.0))
            eval_dir = os.path.join(results_dir, "evaluation_metrics")
            out_res = {
                "status": "done",
                "accuracy": acc,
                "invoker": invoker_name,
                "results_image": os.path.join(eval_dir, "results.png"),
                "confusion_matrix_image": os.path.join(eval_dir, "confusion_matrix.png"),
                "results_csv": os.path.join(eval_dir, "results.csv"),
            }
            if isinstance(context, TrainingContext):
                context.training_results = out_res
                context.status = "done"
            return out_res
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
