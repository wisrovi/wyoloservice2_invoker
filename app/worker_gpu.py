"""Worker Invoker Celery module and task dispatcher.

Bridges Celery queues to Docker/K8s container execution and WPipe state pipelines.
"""

import os
import threading
from typing import Any, Dict

import redis
import yaml
from celery import Task
from celery.signals import worker_ready
from celery_config import app
from pipelines import create_posttrain_pipeline, create_pretrain_pipeline, create_training_pipeline
from services.docker_pull_service import execute_force_docker_pull
from services.gpu_pause_monitor import check_gpu_health, pause_monitor_thread
from services.gpu_task_executor import (
    acquire_concurrency_lock,
    display_welcome_banner,
    print_task_banner,
    record_active_study_telemetry,
)
from services.optuna_executor import run_optuna_study
from states.run_training import resolve_training_timeouts

VERSION = "v2.3.7"
PRIVATE_QUEUE = os.getenv("WORKER_HOST", "unknown")

CONFIG: dict[str, Any] = {}
if os.path.exists("config.yaml"):
    with open("config.yaml", encoding="utf-8") as f:
        cfg_data = yaml.safe_load(f)
        if isinstance(cfg_data, dict):
            CONFIG = cfg_data.get("worker", {})

pipe_pretrain = create_pretrain_pipeline(CONFIG)
pipe_train = create_training_pipeline(CONFIG)
pipe_posttrain = create_posttrain_pipeline(CONFIG)

display_welcome_banner(VERSION, PRIVATE_QUEUE)


def complete_train(training_config: dict[str, Any]) -> dict[str, Any]:
    """Execute complete workflow: EDA, Optuna training, and post-train analysis.

    Args:
        training_config (Dict[str, Any]): Full training job parameters.

    Returns:
        Dict[str, Any]: Unified execution metrics and evaluation results.
    """
    res: dict[str, Any] = {}
    eda_out = pipe_pretrain.run(training_config)
    if isinstance(eda_out, dict):
        res.update(eda_out)

    train_out = run_optuna_study(training_config, CONFIG, pipe_train)
    if isinstance(train_out, dict):
        res.update(train_out)

    training_config.update(res)
    post_out = pipe_posttrain.run(training_config)
    if isinstance(post_out, dict):
        res.update(post_out)
    return res


@app.task(name="tasks.train_on_gpu", bind=True)
def train_on_gpu(self: Task, training_config: dict[str, Any]) -> dict[str, Any]:
    """Execute distributed model training with Optuna optimization on GPU.

    Args:
        self (Task): Bound Celery task instance.
        training_config (Dict[str, Any]): Job parameters mapping.

    Returns:
        Dict[str, Any]: Completed metrics and artifact references.
    """
    invoker_name = PRIVATE_QUEUE
    task_id = self.request.id
    study_id = training_config.get("study_id")
    user_id = str(training_config.get("user_id", "unknown"))

    healthy, msg = check_gpu_health()
    if not healthy:
        err = f"Host GPU is unhealthy on node {invoker_name}: {msg}"
        self.update_state(state="FAILURE", meta={"error": err, "invoker": invoker_name})
        raise RuntimeError(err)

    redis_ttl = int(resolve_training_timeouts(training_config, CONFIG)["timeout_seconds"]) * 2
    r_cli = redis.from_url(app.conf.broker_url)
    acquired, holder = acquire_concurrency_lock(r_cli, task_id, invoker_name, redis_ttl)
    if not acquired:
        return {"status": "skipped_duplicate", "invoker": invoker_name, "message": f"Running on {holder}"}

    self.update_state(state="RUNNING", meta={"status": "Starting Executor", "invoker": invoker_name})
    print_task_banner(task_id, user_id, study_id, invoker_name, VERSION)
    if study_id:
        record_active_study_telemetry(r_cli, str(study_id), task_id, invoker_name, redis_ttl)

    try:
        result = complete_train(training_config)
        if isinstance(result, dict) and "llm_report" in result:
            self.update_state(state="SUCCESS", meta={"status": "completed", "accuracy": result.get("accuracy", 0.0)})
        return result
    finally:
        if study_id:
            try:
                r_cli.delete(f"study:{study_id}:active_trial")
            except Exception:
                pass


@app.task(name="tasks.train_on_gpu_simple", bind=True)
def train_on_gpu_simple(self: Task, training_config: dict[str, Any]) -> dict[str, Any]:
    """Execute single training run without Optuna hyperparameter optimization.

    Args:
        self (Task): Bound Celery task instance.
        training_config (Dict[str, Any]): Training configuration mapping.

    Returns:
        Dict[str, Any]: Evaluation metrics and results dictionary.

    Raises:
        RuntimeError: If the GPU is unhealthy.
    """
    healthy, msg = check_gpu_health()
    if not healthy:
        raise RuntimeError(f"GPU unhealthy: {msg}")
    return pipe_train.run(training_config)


@app.task(name="force_docker_pull")
def force_docker_pull(state: dict[str, Any], image_name: str) -> dict[str, Any]:
    """Force Docker image pull across cluster nodes.

    Args:
        state (Dict[str, Any]): Task state or parameters dictionary.
        image_name (str): Target container image tag.

    Returns:
        Dict[str, Any]: Pull operation summary.
    """
    return execute_force_docker_pull(image_name)


@app.task(name="run_eda")
def run_eda(config: dict[str, Any]) -> dict[str, Any]:
    """Run exploratory data analysis.

    Args:
        config (Dict[str, Any]): Dataset configuration dictionary.

    Returns:
        Dict[str, Any]: EDA report dictionary.
    """
    return pipe_pretrain.run(config)


@app.task(name="run_llm_analizer")
def run_llm_analizer(config: dict[str, Any]) -> dict[str, Any]:
    """Run post-training LLM analysis.

    Args:
        config (Dict[str, Any]): Evaluation artifacts configuration.

    Returns:
        Dict[str, Any]: LLM diagnostic report dictionary.
    """
    return pipe_posttrain.run(config)


@worker_ready.connect
def setup_pause_monitor(sender: Any = None, **kwargs: Any) -> None:
    """Start background GPU and disk monitor when worker is ready.

    Args:
        sender (Any): Celery worker instance or signal sender.
        **kwargs (Any): Additional event keyword arguments.
    """
    node_name = str(sender.hostname if sender else PRIVATE_QUEUE)
    threading.Thread(
        target=pause_monitor_thread, args=(app, node_name, PRIVATE_QUEUE, CONFIG, VERSION), daemon=True
    ).start()
