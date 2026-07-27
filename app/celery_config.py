# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Dynamic Celery configuration for the Worker Invoker.

This module reads configuration from a YAML file and initializes the Celery
application with appropriate broker, backend, and concurrency settings.
"""

import os
from typing import Any

import yaml
from celery import Celery

# 1. READ YAML FIRST (Source of Truth)
CONFIG_PATH: str = "config.yaml"
config: dict[str, Any] = {}
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)

# 2. Extract Redis URL (Priority: Env > YAML > Default)
# Port and DB are considered static for this service
CONTROL_HOST = os.getenv("CONTROL_HOST", "localhost")
REDIS_PORT = 23437
REDIS_DB = 0

REDIS_URL: str = f"redis://{CONTROL_HOST}:{REDIS_PORT}/{REDIS_DB}"

# 3. Initialize Celery App
app: Celery = Celery("ml_cluster", broker=REDIS_URL, backend=REDIS_URL)

# 4. Celery Advanced Configuration
celery_cfg: dict[str, Any] = config.get("celery", {})
worker_settings: dict[str, Any] = {
    "task_routes": {
        "tasks.manage_study": {"queue": "managers"},
        "tasks.train_on_gpu": {"queue": celery_cfg.get("queue", "gpus")},
    },
    # Concurrency control from YAML
    "worker_concurrency": int(celery_cfg.get("concurrency", 1)),
    # Reliability settings for long-running tasks
    "task_acks_late": True,
    "worker_prefetch_multiplier": 1,
    "result_expires": 86400,  # 24 hours
    "worker_send_task_events": True,  # Try enabling to initialize the dispatcher
}

app.conf.update(worker_settings)

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

init_table = Table(show_header=False, box=None)
init_table.add_row("[bold magenta]━━━ CELERY CONFIGURATION ━━━[/bold magenta]", "")
init_table.add_row("[bold cyan]Queue/Node Name:[/bold cyan]", os.getenv('PRIVATE_QUEUE', 'unknown'))
init_table.add_row("[bold cyan]Broker/Backend URL:[/bold cyan]", REDIS_URL)
init_table.add_row("[bold cyan]Concurrency Limit:[/bold cyan]", str(worker_settings["worker_concurrency"]))
init_table.add_row("[bold cyan]Prefetch Multiplier:[/bold cyan]", str(worker_settings["worker_prefetch_multiplier"]))
init_table.add_row("[bold cyan]Task Routes (Train):[/bold cyan]", worker_settings["task_routes"]["tasks.train_on_gpu"]["queue"])
init_table.add_row("[bold cyan]Acks Late Config:[/bold cyan]", str(worker_settings["task_acks_late"]))
init_table.add_row("[bold cyan]Result Expiry (Sec):[/bold cyan]", f"{worker_settings['result_expires']}s")
init_table.add_row("", "")
init_table.add_row("[bold yellow]━━━ HOST ENVIRONMENT (FOR EXECUTOR) ━━━[/bold yellow]", "")
init_table.add_row("[bold cyan]Host User (USER):[/bold cyan]", os.getenv('USER', 'N/A'))
init_table.add_row("[bold cyan]Worker Host IP (WORKER_HOST):[/bold cyan]", os.getenv('WORKER_HOST', 'N/A'))
init_table.add_row("[bold cyan]CPU Cores (WORKER_CPU_CORES):[/bold cyan]", os.getenv('WORKER_CPU_CORES', 'N/A'))
init_table.add_row("[bold cyan]RAM Memory (WORKER_RAM_MEMORY):[/bold cyan]", os.getenv('WORKER_RAM_MEMORY', 'N/A'))
init_table.add_row("[bold cyan]Max GPU Limit % (MAX_GPU):[/bold cyan]", os.getenv('MAX_GPU', 'N/A'))
init_table.add_row("[bold cyan]Concurrent Trains (NUM_CURRENT_TRAIN):[/bold cyan]", os.getenv('NUM_CURRENT_TRAIN', 'N/A'))

console.print(
    Panel(
        init_table,
        title="[bold green]⚙️  Hive Worker - Celery & Host Environment[/bold green]",
        border_style="green",
        expand=False
    )
)

