"""Worker Invoker Module.

This module acts as a bridge between Celery and the Docker-based Executor.
It receives training tasks, prepares the local environment, launches the
Executor container, and reports results back to the Manager.
"""

import os
from typing import Any
import optuna

from celery import Task
from celery_config import app
from states.run_training import RunTraining
from states.eda import EDA
from states.llm_analizer import LlmAnalizer
from wpipe.pipe import Pipeline
import yaml

PRIVATE_QUEUE = os.getenv("PRIVATE_QUEUE", "unknown")

# Load local worker configuration
CONFIG: dict[str, Any] = {}
if os.path.exists("config.yaml"):
    with open("config.yaml", "r", encoding="utf-8") as f:
        CONFIG = yaml.safe_load(f).get("worker", {})

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


def objetive_function(training_config: dict[str, Any]):
    try:
        resultado = pipe_train.run(training_config)

        return resultado["accuracy"]
    except Exception as exc:
        print(f"Pipeline fallido: {str(exc)}")
        raise exc


def optuna_search(training_config: dict[str, Any]):
    # Priority: Manager config > Local config > Default (1)
    TRIALS_OF_CONFIG = training_config.get("n_trials", CONFIG.get("sweeper", {}).get("n_trials", 1))
    DIRECTION = training_config.get("direction", CONFIG.get("sweeper", {}).get("direction", "maximize"))
    SAMPLER = training_config.get("sampler", CONFIG.get("sweeper", {}).get("sampler", "TPESampler"))
    
    # Study Settings (Crucial for distributed scenario)
    study_name = training_config.get("study_name", f"study_{datetime.now().strftime('%Y%m%d')}")
    
    # Priority: Environment variable > Config file
    storage_url = os.getenv("OPTUNA_DB_URL", CONFIG.get("optuna", {}).get("storage_url"))

    if TRIALS_OF_CONFIG <= 0:
        raise ValueError("Number of trials must be greater than 0")

    if SAMPLER == "TPESampler":
        sampler = optuna.samplers.TPESampler()
    elif SAMPLER == "RandomSampler":
        sampler = optuna.samplers.RandomSampler()
    elif SAMPLER == "CmaEsSampler":
        sampler = optuna.samplers.CmaEsSampler()
    else:
        raise ValueError("Invalid sampler")

    if DIRECTION == "maximize":
        direction = optuna.study.StudyDirection.MAXIMIZE
    elif DIRECTION == "minimize":
        direction = optuna.study.StudyDirection.MINIMIZE
    else:
        raise ValueError("Invalid direction")

    # Connect to the distributed database
    study = optuna.create_study(
        study_name=study_name, 
        direction=direction, 
        sampler=sampler,
        storage=storage_url,
        load_if_exists=True
    )
    
    study.optimize(
        objetive_function,
        n_trials=TRIALS_OF_CONFIG,
        show_progress_bar=True,
    )
    return study.best_params


@app.task(name="tasks.train_on_gpu", bind=True)
def train_on_gpu(self: Task, training_config: dict[str, Any]):
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

    print(
        f"--- [INVOKER:{invoker_name}] Task {self.request.id} started for user: {user_id} ---"
    )

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

    print(
        f"--- [INVOKER:{invoker_name}] Task {self.request.id} completed for user: {user_id} ---"
    )

    return resultado
