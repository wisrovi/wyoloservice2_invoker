# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Worker Invoker Module.

This module acts as a bridge between Celery and the Docker-based Executor.
It receives training tasks, prepares the local environment, launches the
Executor container, and reports results back to the Manager.
"""

import os
import json
import time
import redis
from datetime import datetime
from typing import Any, Dict

import optuna
import yaml
from celery import Task
from celery_config import app
from states.eda import EDA
from states.llm_analizer import LlmAnalizer
from states.run_training import RunTraining
from wpipe.pipe import Pipeline


VERSION = "v1.0.0"
PRIVATE_QUEUE = os.getenv("WORKER_HOST", "unknown")

# Load local worker configuration
CONFIG: dict[str, Any] = {}
if os.path.exists("config.yaml"):
    with open("config.yaml", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)
        if config_data:
            CONFIG = config_data.get("worker", {})

pipe_pretrain = Pipeline()
pipe_pretrain.set_steps(
    [
        (EDA(CONFIG), EDA.NAME, EDA.VERSION),
    ]
)

pipe_train = Pipeline()
pipe_train.set_steps(
    [
        (RunTraining(CONFIG), RunTraining.NAME, RunTraining.VERSION),
    ]
)

pipe_posttrain = Pipeline()
pipe_posttrain.set_steps(
    [
        (LlmAnalizer(CONFIG), LlmAnalizer.NAME, LlmAnalizer.VERSION),
    ]
)


def objetive_function(training_config: dict[str, Any]) -> float:
    """Objective function for Optuna optimization.

    Args:
        training_config: Configuration for the training trial.

    Returns:
        float: The accuracy metric achieved in the trial.
    """
    try:
        resultado = pipe_train.run(training_config)

        return float(resultado.get("accuracy", 0.0))
    except Exception as exc:
        print(f"Pipeline fallido: {str(exc)}")
        raise exc


def optuna_search(training_config: dict[str, Any]) -> dict[str, Any]:
    """Perform hyperparameter search using Optuna.

    Args:
        training_config: Base configuration for the search.

    Returns:
        Dict[str, Any]: The best parameters found during search.
    """
    # Priority: Manager config > Local config > Default (1)
    trials_count = training_config.get("n_trials", CONFIG.get("sweeper", {}).get("n_trials", 1))
    direction_str = training_config.get("direction", CONFIG.get("sweeper", {}).get("direction", "maximize"))
    sampler_name = training_config.get("sampler", CONFIG.get("sweeper", {}).get("sampler", "TPESampler"))

    # Study Settings (Crucial for distributed scenario)
    study_name = training_config.get("study_name", f"study_{datetime.now().strftime('%Y%m%d')}")

    # Priority: Environment variable > Config file
    base_url = "postgresql://postgres:postgres@<IP>:23436/wyoloservice"
    control_host = os.getenv("CONTROL_HOST", "localhost")
    storage_url = base_url.replace("<IP>", control_host)

    if trials_count <= 0:
        raise ValueError("Number of trials must be greater than 0")

    if sampler_name == "TPESampler":
        sampler = optuna.samplers.TPESampler()
    elif sampler_name == "RandomSampler":
        sampler = optuna.samplers.RandomSampler()
    elif sampler_name == "CmaEsSampler":
        sampler = optuna.samplers.CmaEsSampler()
    else:
        raise ValueError("Invalid sampler")

    if direction_str == "maximize":
        direction = optuna.study.StudyDirection.MAXIMIZE
    elif direction_str == "minimize":
        direction = optuna.study.StudyDirection.MINIMIZE
    else:
        raise ValueError("Invalid direction")

    # Connect to the distributed database
    study = optuna.create_study(
        study_name=study_name,
        direction=direction,
        sampler=sampler,
        storage=storage_url,
        load_if_exists=True,
    )

    study.optimize(
        objetive_function,
        n_trials=trials_count,
        show_progress_bar=True,
    )
    return study.best_params


@app.task(name="tasks.train_on_gpu", bind=True)
def train_on_gpu(self: Task, training_config: dict[str, Any]) -> dict[str, Any]:
    """Orchestrates the execution of the training EXECUTOR container.

    This task creates a temporary workspace, delivers configuration to the
    Executor via a shared volume, waits for the container to finish, and
    extracts the final metric.

    Args:
        self (Task): The Celery task instance (bound).
        training_config (dict[str, Any]): The configuration for the training trial.

    Returns:
        dict[str, Any]: A dictionary containing the completion status and accuracy.

    Raises:
        Exception: If the executor fails or results are missing.
    """
    invoker_name = os.getenv("PRIVATE_QUEUE", "unknown")
    user_id: str = training_config.get("user_id", "unknown")
    study_id = training_config.get("study_id")

    print("VERSION: {VERSION}")
    print(f"--- [INVOKER:{invoker_name}] Task {self.request.id} started for user: {user_id} ---")

    redis_client = None
    if study_id:
        try:
            redis_client = redis.from_url(app.conf.broker_url)
            active_info = {
                "invoker": invoker_name,
                "trial_id": self.request.id,
                "start_time": time.time()
            }
            redis_client.set(f"study:{study_id}:active_trial", json.dumps(active_info), ex=3600)
            redis_client.set(f"study:{study_id}:invoker", invoker_name, ex=86400)
            redis_client.sadd(f"study:{study_id}:all_invokers", invoker_name)
            redis_client.expire(f"study:{study_id}:all_invokers", 86400)
        except Exception as e:
            print(f"Warning: Could not set active trial or invoker telemetry in Redis: {e}")

    try:
        try:
            resultado = pipe_pretrain.run(training_config)
        except Exception as exc:
            print(f"Pipeline fallido: {str(exc)}")
            raise exc

        try:
            resultado = optuna_search(training_config)
        except Exception as exc:
            print(f"Pipeline fallido: {str(exc)}")
            raise exc

        try:
            resultado = pipe_posttrain.run(training_config)
        except Exception as exc:
            print(f"Pipeline fallido: {str(exc)}")
            raise exc

        print(f"--- [INVOKER:{invoker_name}] Task {self.request.id} completed for user: {user_id} ---")
        if study_id and redis_client:
            try:
                redis_client.delete(f"study:{study_id}:active_trial")
            except Exception as e:
                print(f"Warning: Could not delete active trial in Redis: {e}")
        return resultado

    except Exception as exc:
        if study_id and redis_client:
            try:
                redis_client.delete(f"study:{study_id}:active_trial")
                error_info = {
                    "invoker": invoker_name,
                    "error": str(exc),
                    "timestamp": time.time()
                }
                redis_client.set(f"study:{study_id}:error", json.dumps(error_info), ex=86400)
            except Exception as e:
                print(f"Warning: Could not log error to Redis: {e}")
        raise exc


@app.task(name="tasks.train_on_gpu_simple", bind=True)
def train_on_gpu_simple(self: Task, training_config: dict[str, Any]) -> dict[str, Any]:
    """Simplified task that runs the Executor directly without Optuna.

    Useful for testing the Invoker -> Executor -> results.json flow.

    Args:
        self: Celery task instance.
        training_config: Training configuration.

    Returns:
        dict: Execution results.
    """
    invoker_name = os.getenv("PRIVATE_QUEUE", "unknown")
    user_id = training_config.get("user_id", "unknown")
    study_id = training_config.get("study_id")

    print(f"--- [INVOKER:{invoker_name}] SIMPLE Task {self.request.id} started for user: {user_id} ---")

    redis_client = None
    if study_id:
        try:
            redis_client = redis.from_url(app.conf.broker_url)
            active_info = {
                "invoker": invoker_name,
                "trial_id": self.request.id,
                "start_time": time.time()
            }
            redis_client.set(f"study:{study_id}:active_trial", json.dumps(active_info), ex=3600)
            redis_client.set(f"study:{study_id}:invoker", invoker_name, ex=86400)
            redis_client.sadd(f"study:{study_id}:all_invokers", invoker_name)
            redis_client.expire(f"study:{study_id}:all_invokers", 86400)
        except Exception as e:
            print(f"Warning: Could not set active trial or invoker telemetry in Redis: {e}")

    try:
        run_training = RunTraining(CONFIG)
        resultado = run_training(training_config)

        accuracy = resultado.get("accuracy", "N/A")
        print(f"--- [INVOKER:{invoker_name}] SIMPLE Task {self.request.id} completed. Accuracy: {accuracy} ---")
        
        if study_id and redis_client:
            try:
                redis_client.delete(f"study:{study_id}:active_trial")
            except Exception as e:
                print(f"Warning: Could not delete active trial in Redis: {e}")
        return resultado

    except Exception as exc:
        print(f"--- [INVOKER:{invoker_name}] SIMPLE Task failed: {str(exc)} ---")
        if study_id and redis_client:
            try:
                redis_client.delete(f"study:{study_id}:active_trial")
                error_info = {
                    "invoker": invoker_name,
                    "error": str(exc),
                    "timestamp": time.time()
                }
                redis_client.set(f"study:{study_id}:error", json.dumps(error_info), ex=86400)
            except Exception as e:
                print(f"Warning: Could not log error to Redis: {e}")
        raise exc
