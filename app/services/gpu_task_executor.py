"""Celery GPU task orchestration and telemetry tracking service."""

import json
import os
import time
from typing import Any, Callable, Dict, Optional, Tuple
import redis
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from .gpu_pause_monitor import check_gpu_health


def display_welcome_banner(version: str, private_queue: str) -> None:
    """Display startup diagnostics and host binding banner.

    Args:
        version (str): Application release version.
        private_queue (str): Worker host private queue identifier.
    """
    console = Console()
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Icon", justify="center", style="bold")
    table.add_column("Label", justify="right", style="bold cyan")
    table.add_column("Value", justify="left")
    table.add_row("📌", "Version:", f"[bold green]{version}[/bold green]")
    table.add_row("🌐", "Host (PRIVATE_QUEUE):", f"[bold yellow]{private_queue}[/bold yellow]")
    table.add_row("⏰", "Started At:", f"[dim white]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim white]")
    console.print(
        Panel(
            table,
            title="[bold bright_green]⚡ WORKER INVOKER INITIALIZED [/bold bright_green]",
            border_style="bright_green",
        )
    )


def acquire_concurrency_lock(redis_client: Any, task_id: str, invoker_name: str, redis_ttl: int) -> Tuple[bool, str]:
    """Attempt to acquire a unique execution lock in Redis for task_id.

    Args:
        redis_client (Any): Connected Redis client.
        task_id (str): Unique task identifier.
        invoker_name (str): Current node identifier.
        redis_ttl (int): Lock lease duration in seconds.

    Returns:
        Tuple[bool, str]: (is_acquired, current_holder_name).
    """
    lock_key = f"wyolo:task_lock:{task_id}"
    try:
        if redis_client.set(lock_key, invoker_name, nx=True, ex=redis_ttl):
            return True, invoker_name
        existing = redis_client.get(lock_key)
        holder = existing.decode() if isinstance(existing, bytes) else str(existing or "unknown")
        return False, holder
    except Exception:
        return True, invoker_name


def record_active_study_telemetry(redis_client: Any, study_id: str, task_id: str, invoker_name: str, redis_ttl: int) -> None:
    """Record worker host telemetry in Redis under study namespace.

    Args:
        redis_client (Any): Connected Redis client.
        study_id (str): Study identifier.
        task_id (str): Active trial task identifier.
        invoker_name (str): Current node identifier.
        redis_ttl (int): Telemetry TTL in seconds.
    """
    if not redis_client or not study_id:
        return
    try:
        worker_host = os.getenv("WORKER_HOST", "unknown")
        worker_hostname = os.getenv("WORKER_HOSTNAME", "unknown")
        invoker_details = {
            "invoker_queue": invoker_name,
            "worker_host": worker_host,
            "worker_hostname": worker_hostname,
            "timestamp": time.time(),
        }
        active_info = {"invoker": invoker_name, "trial_id": task_id, "start_time": time.time(), "details": invoker_details}
        redis_client.set(f"study:{study_id}:active_trial", json.dumps(active_info), ex=redis_ttl)
        redis_client.set(f"study:{study_id}:invoker_details", json.dumps(invoker_details), ex=redis_ttl)
        redis_client.set(f"study:{study_id}:invoker", f"{invoker_name} (IP: {worker_host})", ex=redis_ttl)
        redis_client.sadd(f"study:{study_id}:all_invokers", invoker_name)
        redis_client.expire(f"study:{study_id}:all_invokers", redis_ttl)
    except Exception as exc:
        print(f"Warning: Could not record active study telemetry in Redis: {exc}")


def print_task_banner(task_id: str, user_id: str, study_id: Optional[str], invoker_name: str, version: str) -> None:
    """Print visual task start banner on console.

    Args:
        task_id (str): Celery task ID.
        user_id (str): Submitting user ID.
        study_id (Optional[str]): Optuna study ID.
        invoker_name (str): Worker node name.
        version (str): Worker version.
    """
    console = Console()
    table = Table(show_header=False, box=None)
    table.add_row("[bold cyan]Task ID:[/bold cyan]", str(task_id))
    table.add_row("[bold cyan]User ID:[/bold cyan]", str(user_id))
    table.add_row("[bold cyan]Study ID:[/bold cyan]", str(study_id))
    table.add_row("[bold cyan]Version:[/bold cyan]", str(version))
    console.print(
        Panel(table, title=f"[bold yellow]⚡ [INVOKER:{invoker_name}] Task Started[/bold yellow]", border_style="yellow", expand=False)
    )
