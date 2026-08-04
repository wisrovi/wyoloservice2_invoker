"""Worker Invoker Module.

This module acts as a bridge between Celery and the Docker-based Executor.
It receives training tasks, prepares the local environment, launches the
Executor container, and reports results back to the Manager.
"""

import json
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict

import optuna
import redis
import yaml
from celery import Task
from celery.signals import worker_ready
from celery_config import app
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from states.eda import EDA
from states.llm_analizer import LlmAnalizer
from states.run_training import RunTraining
from wpipe.pipe import Pipeline

# INVOKER VERSION
VERSION = "v1.8.1"
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


def _suggest_from_space(
    trial: optuna.trial.Trial, search_space: dict[str, Any], prefix: str = ""
) -> dict[str, Any]:
    suggested = {}
    for key, val in search_space.items():
        param_name = f"{prefix}{key}"
        if isinstance(val, dict):
            suggested[key] = _suggest_from_space(trial, val, prefix=f"{param_name}:")
        elif isinstance(val, list) and len(val) >= 2:
            dist_type = val[0]
            if dist_type == "choice":
                choices = val[1] if isinstance(val[1], list) else val[1:]
                suggested[key] = trial.suggest_categorical(param_name, choices)
            elif dist_type == "uniform" and len(val) >= 3:
                suggested[key] = trial.suggest_float(
                    param_name, float(val[1]), float(val[2])
                )
            elif dist_type == "loguniform" and len(val) >= 3:
                suggested[key] = trial.suggest_float(
                    param_name, float(val[1]), float(val[2]), log=True
                )
            elif dist_type == "intuniform" and len(val) >= 3:
                suggested[key] = trial.suggest_int(param_name, int(val[1]), int(val[2]))
    return suggested


def _merge_configs(base: dict[str, Any], suggested: dict[str, Any]) -> dict[str, Any]:
    for key, val in suggested.items():
        if isinstance(val, dict) and key in base and isinstance(base[key], dict):
            _merge_configs(base[key], val)
        else:
            base[key] = val
    return base


def optuna_search(training_config: dict[str, Any]) -> dict[str, Any]:
    """Perform hyperparameter search using Optuna.

    Args:
        training_config: Base configuration for the search.

    Returns:
        Dict[str, Any]: The best parameters found during search.
    """
    # Priority: Manager config > Local config > Default (1)
    trials_count = training_config.get(
        "n_trials", CONFIG.get("sweeper", {}).get("n_trials", 1)
    )
    direction_str = training_config.get(
        "direction", CONFIG.get("sweeper", {}).get("direction", "maximize")
    )
    sampler_name = training_config.get(
        "sampler", CONFIG.get("sweeper", {}).get("sampler", "TPESampler")
    )
    search_space = training_config.get("sweeper", {}).get("search_space", {})

import hashlib

# Study Settings (Crucial for distributed scenario)
base_study_name = training_config.get(
    "study_name", f"study_{datetime.now().strftime('%Y%m%d')}"
)
# Include hash of search space to avoid conflicts when search space changes
space_hash = hashlib.md5(json.dumps(search_space, sort_keys=True).encode()).hexdigest()[:8]
study_name = f"{base_study_name}_{space_hash}"

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

    def objective(trial: optuna.trial.Trial) -> float:
        # Deep copy config to ensure trials are isolated
        trial_config = json.loads(json.dumps(training_config))
        if search_space:
            suggested = _suggest_from_space(trial, search_space)
            trial_config = _merge_configs(trial_config, suggested)

        try:
            resultado = pipe_train.run(trial_config)
            return float(resultado.get("accuracy", 0.0))
        except Exception as exc:
            print(f"Pipeline fallido en trial: {str(exc)}")
            raise exc

    study.optimize(
        objective,
        n_trials=trials_count,
        show_progress_bar=True,
    )
    return study.best_params


def welcome():
    console = Console()

    # Tabla estructurada con espaciado óptimo
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Icon", justify="center", style="bold")
    table.add_column("Label", justify="right", style="bold cyan")
    table.add_column("Value", justify="left")

    # Mapeo de filas con formato visual diferenciado
    table.add_row("📌", "Version:", f"[bold green]{VERSION}[/bold green]")
    table.add_row(
        "🌐",
        "Host (PRIVATE_QUEUE):",
        f"[bold yellow]{PRIVATE_QUEUE}[/bold yellow]",
    )
    table.add_row(
        "⏰",
        "Started At:",
        f"[dim white]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim white]",
    )

    # Panel principal
    console.print(
        Panel(
            table,
            title="[bold bright_green]⚡ WORKER INVOKER INITIALIZED [/bold bright_green]",
            subtitle="[dim green]● Online & Listening[/dim green]",
            border_style="bright_green",
            padding=(1, 3),
            expand=False,
        )
    )


welcome()


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
    invoker_name = PRIVATE_QUEUE
    user_id: str = training_config.get("user_id", "unknown")
    study_id = training_config.get("study_id")

    self.update_state(
        state="RUNNING",
        meta={
            "status": "Starting Executor",
            "invoker": invoker_name,
        },
    )

    console = Console()

    task_table = Table(show_header=False, box=None)
    task_table.add_row("[bold cyan]Task ID:[/bold cyan]", self.request.id)
    task_table.add_row("[bold cyan]User ID:[/bold cyan]", user_id)
    task_table.add_row("[bold cyan]Study ID:[/bold cyan]", str(study_id))
    task_table.add_row("[bold cyan]Version:[/bold cyan]", VERSION)

    console.print(
        Panel(
            task_table,
            title=f"[bold yellow]⚡ [INVOKER:{invoker_name}] Task Started[/bold yellow]",
            border_style="yellow",
            expand=False,
        )
    )

    redis_client = None
    if study_id:
        try:
            redis_client = redis.from_url(app.conf.broker_url)
            # Retrieve host environment variables for richer telemetry
            worker_host = os.getenv("WORKER_HOST", "unknown")
            worker_hostname = os.getenv("WORKER_HOSTNAME", "unknown")
            worker_os = os.getenv("WORKER_OS", "unknown")
            worker_cpus = os.getenv("WORKER_CPU_CORES", "unknown")
            worker_gpu_count = os.getenv("WORKER_GPU_COUNT", "0")
            worker_gpu_model = os.getenv("WORKER_GPU_MODEL", "unknown")

            invoker_details = {
                "invoker_queue": invoker_name,
                "worker_host": worker_host,
                "worker_hostname": worker_hostname,
                "worker_os": worker_os,
                "worker_cpu_cores": worker_cpus,
                "worker_gpu_count": worker_gpu_count,
                "worker_gpu_model": worker_gpu_model,
                "timestamp": time.time(),
            }

            active_info = {
                "invoker": invoker_name,
                "trial_id": self.request.id,
                "start_time": time.time(),
                "details": invoker_details,
            }
            redis_client.set(
                f"study:{study_id}:active_trial", json.dumps(active_info), ex=3600
            )
            # Store full JSON details in a dedicated key
            redis_client.set(
                f"study:{study_id}:invoker_details",
                json.dumps(invoker_details),
                ex=86400,
            )
            # Store an enriched, readable string in the classic key for UI compatibility
            invoker_readable = (
                f"{invoker_name} (IP: {worker_host} | Host: {worker_hostname})"
            )
            redis_client.set(f"study:{study_id}:invoker", invoker_readable, ex=86400)

            redis_client.sadd(f"study:{study_id}:all_invokers", invoker_name)
            redis_client.expire(f"study:{study_id}:all_invokers", 86400)
        except Exception as e:
            print(
                f"Warning: Could not set active trial or invoker telemetry in Redis: {e}"
            )

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

        console.print(
            Panel(
                f"[bold green]✔ Task {self.request.id} completed successfully for user: {user_id}[/bold green]",
                title=f"[bold green]⚡ [INVOKER:{invoker_name}] Task Completed[/bold green]",
                border_style="green",
                expand=False,
            )
        )
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
                    "timestamp": time.time(),
                }
                redis_client.set(
                    f"study:{study_id}:error", json.dumps(error_info), ex=86400
                )
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
    invoker_name = PRIVATE_QUEUE
    user_id = training_config.get("user_id", "unknown")
    study_id = training_config.get("study_id")

    console = Console()

    task_table = Table(show_header=False, box=None)
    task_table.add_row("[bold cyan]Task ID:[/bold cyan]", self.request.id)
    task_table.add_row("[bold cyan]User ID:[/bold cyan]", user_id)
    task_table.add_row("[bold cyan]Study ID:[/bold cyan]", str(study_id))
    task_table.add_row("[bold cyan]Mode:[/bold cyan]", "SIMPLE (No Optuna)")
    task_table.add_row("[bold cyan]Version:[/bold cyan]", VERSION)

    console.print(
        Panel(
            task_table,
            title=f"[bold yellow]⚡ [INVOKER:{invoker_name}] Simple Task Started[/bold yellow]",
            border_style="yellow",
            expand=False,
        )
    )

    redis_client = None
    if study_id:
        try:
            redis_client = redis.from_url(app.conf.broker_url)
            # Retrieve host environment variables for richer telemetry
            worker_host = os.getenv("WORKER_HOST", "unknown")
            worker_hostname = os.getenv("WORKER_HOSTNAME", "unknown")
            worker_os = os.getenv("WORKER_OS", "unknown")
            worker_cpus = os.getenv("WORKER_CPU_CORES", "unknown")
            worker_gpu_count = os.getenv("WORKER_GPU_COUNT", "0")
            worker_gpu_model = os.getenv("WORKER_GPU_MODEL", "unknown")

            invoker_details = {
                "invoker_queue": invoker_name,
                "worker_host": worker_host,
                "worker_hostname": worker_hostname,
                "worker_os": worker_os,
                "worker_cpu_cores": worker_cpus,
                "worker_gpu_count": worker_gpu_count,
                "worker_gpu_model": worker_gpu_model,
                "timestamp": time.time(),
            }

            active_info = {
                "invoker": invoker_name,
                "trial_id": self.request.id,
                "start_time": time.time(),
                "details": invoker_details,
            }
            redis_client.set(
                f"study:{study_id}:active_trial", json.dumps(active_info), ex=3600
            )
            # Store full JSON details in a dedicated key
            redis_client.set(
                f"study:{study_id}:invoker_details",
                json.dumps(invoker_details),
                ex=86400,
            )
            # Store an enriched, readable string in the classic key for UI compatibility
            invoker_readable = (
                f"{invoker_name} (IP: {worker_host} | Host: {worker_hostname})"
            )
            redis_client.set(f"study:{study_id}:invoker", invoker_readable, ex=86400)

            redis_client.sadd(f"study:{study_id}:all_invokers", invoker_name)
            redis_client.expire(f"study:{study_id}:all_invokers", 86400)
        except Exception as e:
            print(
                f"Warning: Could not set active trial or invoker telemetry in Redis: {e}"
            )

    try:
        self.update_state(
            state="RUNNING",
            meta={
                "status": "Launching Docker Executor",
                "invoker": invoker_name,
            },
        )
        run_training = RunTraining(CONFIG)
        training_config["task_id"] = self.request.id
        self.update_state(
            state="PROGRESS",
            meta={
                "status": "Starting executor",
                "epoch": 0,
                "gpu": "N/A",
                "ram": "N/A",
                "cpu": "N/A",
            },
        )
        resultado = run_training(training_config)

        self.update_state(
            state="PROGRESS",
            meta={
                "status": "Executor finished",
                "epoch": "Done",
                "gpu": "N/A",
                "ram": "N/A",
                "cpu": "N/A",
            },
        )

        accuracy = resultado.get("accuracy", "N/A")
        console.print(
            Panel(
                f"[bold green]✔ Task {self.request.id} completed. Accuracy: {accuracy}[/bold green]",
                title=f"[bold green]⚡ [INVOKER:{invoker_name}] Simple Task Completed[/bold green]",
                border_style="green",
                expand=False,
            )
        )

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
                    "timestamp": time.time(),
                }
                redis_client.set(
                    f"study:{study_id}:error", json.dumps(error_info), ex=86400
                )
            except Exception as e:
                print(f"Warning: Could not log error to Redis: {e}")
        raise exc


def pause_monitor_thread(
    app_inst, node_name: str, private_queue_ip: str, default_hours: float
):
    """Monitors the pause state in Redis and cancels/adds public queues dynamically."""
    print(
        f"[PAUSE MONITOR] Starting monitor thread for node: {node_name} (IP: {private_queue_ip})"
    )

    # Celery public queues to manage
    public_queues = ["gpus_high", "gpus_medium", "gpus_low"]

    # Start as active
    public_queues_active = True

    while True:
        try:
            # We connect/reconnect each time or reuse connection
            redis_client = redis.from_url(app_inst.conf.broker_url)

            state_key = f"invoker:{private_queue_ip}:pause_state"
            until_key = f"invoker:{private_queue_ip}:pause_until"

            state_bytes = redis_client.get(state_key)
            state = state_bytes.decode("utf-8") if state_bytes else "active"

            now = time.time()

            # Check temporal pause expiration
            if state == "paused_temporal":
                until_bytes = redis_client.get(until_key)
                if until_bytes:
                    pause_until = float(until_bytes.decode("utf-8"))
                    if now >= pause_until:
                        # Expiró la pausa temporal
                        redis_client.set(state_key, "active")
                        redis_client.delete(until_key)
                        state = "active"
                        print(
                            f"[PAUSE MONITOR] Temporal pause expired. Activating node {node_name}"
                        )
                else:
                    # Si está en paused_temporal pero no tiene hasta cuándo,
                    # por seguridad lo reactivamos.
                    redis_client.set(state_key, "active")
                    state = "active"

            # Apply pause or active state
            if state in ("paused_perpetual", "paused_temporal"):
                if public_queues_active:
                    print(
                        f"[PAUSE MONITOR] Node {node_name} entering PAUSE. Cancelling public queues..."
                    )
                    for q in public_queues:
                        app_inst.control.cancel_consumer(q, destination=[node_name])
                    public_queues_active = False
            else:  # active o cualquier otra cosa
                if not public_queues_active:
                    print(
                        f"[PAUSE MONITOR] Node {node_name} entering ACTIVE. Resuming public queues..."
                    )
                    for q in public_queues:
                        app_inst.control.add_consumer(q, destination=[node_name])
                    public_queues_active = True

        except Exception as e:
            print(f"[PAUSE MONITOR] Error in monitor loop: {e}")

        time.sleep(10)


@worker_ready.connect
def setup_pause_monitor(sender=None, **kwargs):
    """Initializes the background pause monitor thread and registers worker telemetry when ready."""
    if sender is None:
        return

    node_name = sender.hostname
    # Get the worker host IP from PRIVATE_QUEUE environment or sender name
    private_queue_ip = os.getenv("WORKER_HOST", "unknown")
    default_hours = float(CONFIG.get("pause_duration_hours", 4))

    # Register invoker metadata in Redis on startup
    try:
        redis_client = redis.from_url(app.conf.broker_url)
        worker_host = os.getenv("WORKER_HOST", "unknown")
        worker_hostname = os.getenv("WORKER_HOSTNAME", "unknown")
        worker_os = os.getenv("WORKER_OS", "unknown")
        worker_cpus = os.getenv("WORKER_CPU_CORES", "unknown")
        worker_gpu_count = os.getenv("WORKER_GPU_COUNT", "0")
        worker_gpu_model = os.getenv("WORKER_GPU_MODEL", "unknown")

        # Calculate limits allocated for the executor
        import multiprocessing

        cpu_pct = float(CONFIG.get("cpu_limit_pct", 0.85))
        mem_pct = float(CONFIG.get("mem_limit_pct", 0.60))

        # CPU allocation calculation
        cores_env = os.getenv("WORKER_CPU_CORES_AVAILABLE") or os.getenv(
            "WORKER_CPU_CORES"
        )
        if cores_env:
            try:
                allocated_cpus = float(cores_env)
            except ValueError:
                allocated_cpus = float(multiprocessing.cpu_count() * cpu_pct)
        else:
            allocated_cpus = float(multiprocessing.cpu_count() * cpu_pct)

        # RAM allocation calculation
        ram_env = os.getenv("WORKER_RAM_MEMORY")
        allocated_ram = (
            ram_env if ram_env else f"{int(mem_pct * 100)}% of total host RAM"
        )

        metadata = {
            "version": VERSION,
            "worker_host": worker_host,
            "worker_hostname": worker_hostname,
            "worker_os": worker_os,
            "worker_cpu_cores": worker_cpus,
            "worker_gpu_count": worker_gpu_count,
            "worker_gpu_model": worker_gpu_model,
            "executor_allocated_cpus": f"{allocated_cpus:.2f}",
            "executor_allocated_ram": allocated_ram,
            "executor_cpu_limit_pct": cpu_pct,
            "executor_mem_limit_pct": mem_pct,
            "startup_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "online",
        }

        redis_client.set(f"invoker:{worker_host}:version", json.dumps(metadata))
        print(
            f"[METADATA REGISTRATION] Saved host metadata to Redis key 'invoker:{worker_host}:version'"
        )
    except Exception as e:
        print(
            f"[METADATA REGISTRATION] Warning: Failed to save host metadata to Redis: {e}"
        )

    t = threading.Thread(
        target=pause_monitor_thread,
        args=(app, node_name, private_queue_ip, default_hours),
        daemon=True,
    )
    t.start()


from celery.worker.control import control_command


@control_command(
    args=[("image_name", str)],
    signature="Forces the worker to execute a docker pull on the specified image.",
)
def force_docker_pull(state, image_name):
    """Executes a docker pull command on the worker host for the specified image."""
    import subprocess

    print(f"[CONTROL COMMAND] Received force_docker_pull request for: {image_name}")
    try:
        # Run docker pull command to download the updated image from Docker Hub
        result = subprocess.run(
            ["docker", "pull", image_name], capture_output=True, text=True, check=True
        )
        output_str = result.stdout.strip()
        print(f"[CONTROL COMMAND] Successfully pulled image: {image_name}")
        return {"status": "success", "image": image_name, "output": output_str}
    except subprocess.CalledProcessError as err:
        error_msg = f"Docker pull failed: {err.stderr.strip()}"
        print(f"[CONTROL COMMAND] Error: {error_msg}")
        return {"status": "failed", "image": image_name, "error": error_msg}
    except Exception as exc:
        error_msg = f"Unexpected error: {str(exc)}"
        print(f"[CONTROL COMMAND] Error: {error_msg}")
        return {"status": "failed", "image": image_name, "error": error_msg}
