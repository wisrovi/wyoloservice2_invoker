"""Gradio Launcher for the Local Invoker.

This module provides a web interface to submit training tasks directly to
the local Celery-based invoker, bypassing the Manager/API stack. It serves
as a fallback (lifeline) when the full architecture is unavailable.

It persists the YAML configuration in a Redis hash managed via wredis,
auto-detects the invoker's private queue, and offers three queue-target
options.

Typical usage:
    $ python gradio_app.py
"""

from __future__ import annotations

import json
import os

import subprocess
from typing import Any

import gradio as gr
import yaml
from celery import Celery
from wredis import RedisHashManager

import socket

from celery.result import AsyncResult


def get_host_ip() -> str:
    """Get host machine IP from inside Docker."""
    try:
        return socket.gethostbyname("host.docker.internal")
    except Exception:
        return "127.0.0.1"


def build_status_table(epoch, cpu, ram, gpu):
    return (
        f"🖥️ **CPU:** {cpu}% &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"💾 **RAM:** {ram} MB &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"🎮 **GPU:** {gpu}% &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"🔄 **Epoch:** {epoch}"
    )


# ── Constants for Executor ───────────────────────────────────────────
_EXECUTOR_IMAGE: str = "wisrovi/train_service:worker_executor_v1.0.0"
_REQUEST_DIR: str = "/home/wyolo/request"
_EVENTS_DIR: str = "/home/wyolo/events"
_RESULTS_DIR: str = "/results"
_EVALUATION_DIR: str = "/results/evaluation_metrics"
_RESULTS_IMAGE: str = os.path.join(
    _EVALUATION_DIR,
    "results.png",
)

_CONFUSION_MATRIX_IMAGE: str = os.path.join(
    _EVALUATION_DIR,
    "confusion_matrix.png",
)


# ── Constants ──────────────────────────────────────────────────────
_CONTROL_HOST: str = os.getenv("CONTROL_HOST", "127.0.0.1")
_REDIS_PORT: int = 23_437
_REDIS_URL: str = f"redis://{_CONTROL_HOST}:{_REDIS_PORT}/0"

# Gradio Launcher UI Version
GRADIO_VERSION: str = "v1.1.0"

_PRIVATE_QUEUE: str = os.getenv("PRIVATE_QUEUE") or os.getenv("WORKER_HOST") or "default"
if _PRIVATE_QUEUE == "default" and os.getenv("WORKER_HOST"):
    _PRIVATE_QUEUE = os.getenv("WORKER_HOST")

_HASH_KEY: str = f"invoker:{_PRIVATE_QUEUE}:template_invoker"

_celery_app: Celery = Celery(
    "invoker_launcher",
    broker=_REDIS_URL,
    backend=_REDIS_URL,
)
_hm: RedisHashManager | None = None


# ── Local Worker Status & Optuna History ──────────────────────────────────

def get_local_worker_status() -> str:
    """Query Celery active tasks and status of the local worker node."""
    try:
        worker_name = f"celery@wyolo_invoker_{_PRIVATE_QUEUE}"
        inspect = _celery_app.control.inspect([worker_name])
        
        # Ping the worker
        ping = inspect.ping()
        if not ping or worker_name not in ping:
            return (
                "### 🖥️ Local Worker Status\n\n"
                "🔴 **Status:** Offline / Disconnected\n\n"
                f"🎯 **Queue Target:** `{_PRIVATE_QUEUE}`\n\n"
                "⚠️ *Verify that the Celery worker container is running on this host.*"
            )
            
        # Get active tasks
        active = inspect.active()
        active_tasks = active.get(worker_name, []) if active else []
        
        # Get reserved/queued tasks
        reserved = inspect.reserved()
        reserved_tasks = reserved.get(worker_name, []) if reserved else []
        
        # Get worker stats
        stats_all = inspect.stats()
        worker_stats = stats_all.get(worker_name, {}) if stats_all else {}
        pool = worker_stats.get("pool", {})
        concurrency = pool.get("max-concurrency", 1)
        
        status_md = "### 🖥️ Local Worker Status\n\n"
        status_md += "🟢 **Status:** Online\n\n"
        status_md += f"🎯 **Queue Target:** `{_PRIVATE_QUEUE}` &nbsp;&nbsp;|&nbsp;&nbsp; 🚀 **Concurrency:** {concurrency}\n\n"
        
        if active_tasks:
            status_md += "#### ⚡ Active Running Tasks\n"
            for t in active_tasks:
                task_id = t.get("id")
                task_name = t.get("name")
                runtime = t.get("runtime", "N/A")
                status_md += f"* **ID:** `{task_id}` | **Name:** `{task_name}` | **Runtime:** {runtime}s\n"
        else:
            status_md += "💤 **Active Tasks:** None (Idle)\n\n"
            
        if reserved_tasks:
            status_md += f"#### ⏳ Queued Tasks in Buffer: **{len(reserved_tasks)}**\n"
            for t in reserved_tasks:
                status_md += f"* **ID:** `{t.get('id')}` | **Name:** `{t.get('name')}`\n"
                
        return status_md
    except Exception as exc:
        return f"⚠️ **Local Worker Status Error:** {exc}"


def get_optuna_engine():
    default_db_url = f"postgresql://postgres:postgres@{_CONTROL_HOST}:23436/wyoloservice"
    optuna_db_url = os.getenv("OPTUNA_DB_URL", default_db_url)
    from sqlalchemy import create_engine
    return create_engine(optuna_db_url)


def list_optuna_studies() -> list[str]:
    """Fetch all study names from PostgreSQL database."""
    try:
        from sqlalchemy import text
        engine = get_optuna_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT study_name FROM studies ORDER BY study_id DESC"))
            return [row[0] for row in result.fetchall()]
    except Exception as e:
        print(f"Error listing studies: {e}")
        return []


def get_optuna_study_history(study_name: str) -> str:
    """Fetch history and best trial details for a specific Optuna study."""
    if not study_name or not study_name.strip():
        return "⚠️ *Please select or input a valid study name.*"
        
    study_name = study_name.strip()
    try:
        from sqlalchemy import text
        engine = get_optuna_engine()
        
        # 1. Fetch study details
        with engine.connect() as conn:
            study_row = conn.execute(
                text("""
                SELECT s.study_id, sd.direction 
                FROM studies s
                LEFT JOIN study_directions sd ON s.study_id = sd.study_id
                WHERE s.study_name = :study_name
            """),
                {"study_name": study_name}
            ).fetchone()
            
            if not study_row:
                return f"❌ **Study not found:** '{study_name}'"
                
            study_id, direction = study_row
            
            # 2. Fetch the best trial
            best_row = conn.execute(
                text("""
                SELECT t.trial_id, tv.value, t.datetime_start, t.datetime_complete
                FROM trials t
                JOIN trial_values tv ON t.trial_id = tv.trial_id
                WHERE t.study_id = :study_id AND t.state = 'COMPLETE'
                ORDER BY
                    CASE WHEN :direction = 'MAXIMIZE' THEN tv.value END DESC,
                    CASE WHEN :direction = 'MINIMIZE' THEN tv.value END ASC
                LIMIT 1
            """),
                {"study_id": study_id, "direction": direction}
            ).fetchone()
            
            # 3. Fetch all trials
            trials_rows = conn.execute(
                text("""
                SELECT t.trial_id, t.state, tv.value, t.datetime_start, t.datetime_complete
                FROM trials t
                LEFT JOIN trial_values tv ON t.trial_id = tv.trial_id
                WHERE t.study_id = :study_id
                ORDER BY t.trial_id DESC
            """),
                {"study_id": study_id}
            ).fetchall()

        # Build best trial parameters if found
        best_info_md = ""
        if best_row:
            bt_id, bt_value, bt_start, bt_end = best_row
            # Fetch best trial parameters
            with engine.connect() as conn:
                params_rows = conn.execute(
                    text("SELECT param_name, param_value FROM trial_params WHERE trial_id = :trial_id"),
                    {"trial_id": bt_id}
                ).fetchall()
            params_dict = {p[0]: p[1] for p in params_rows}
            params_formatted = ", ".join([f"`{k}`: **{v}**" for k, v in params_dict.items()])
            
            best_info_md = (
                f"### 🏆 Best Trial Found (Trial #{bt_id})\n"
                f"* **Metric Score:** `{bt_value:.5f}` &nbsp;&nbsp;|&nbsp;&nbsp; **Direction:** `{direction}`\n"
                f"* **Hyperparameters:** {params_formatted}\n"
                f"* **Start:** {bt_start} &nbsp;&nbsp;|&nbsp;&nbsp; **End:** {bt_end}\n\n"
            )
        else:
            best_info_md = "### 🏆 Best Trial Found\n*No completed trials yet in this study.*\n\n"

        # Build trials history table
        table_md = "#### 📋 Trials Log\n\n"
        table_md += "| Trial ID | State | Score | Start Time | Parameters |\n"
        table_md += "| :--- | :--- | :--- | :--- | :--- |\n"
        
        for r in trials_rows:
            t_id, t_state, t_value, t_start, t_end = r
            # Fetch params for this trial
            with engine.connect() as conn:
                params_rows = conn.execute(
                    text("SELECT param_name, param_value FROM trial_params WHERE trial_id = :trial_id"),
                    {"trial_id": t_id}
                ).fetchall()
            t_params_dict = {p[0]: p[1] for p in params_rows}
            t_params_formatted = ", ".join([f"`{k}`: {v}" for k, v in t_params_dict.items()])
            
            val_str = f"{t_value:.5f}" if t_value is not None else "-"
            state_emoji = "🟢" if t_state == "COMPLETE" else ("🟡" if t_state == "RUNNING" else "🔴")
            
            table_md += f"| #{t_id} | {state_emoji} {t_state} | **{val_str}** | {t_start} | {t_params_formatted} |\n"

        return f"{best_info_md}{table_md}"
    except Exception as exc:
        return f"❌ **Optuna Connection Error:** {exc}"


# ── Redis ──────────────────────────────────────────────────────────


def _get_hm() -> RedisHashManager | None:
    """Lazy-init and return the RedisHashManager singleton."""
    global _hm  # noqa: PLW0603
    if _hm is None:
        try:
            _hm = RedisHashManager(host=_CONTROL_HOST, port=_REDIS_PORT)
        except Exception:
            _hm = None
    return _hm


def get_telemetry():
    try:
        if not os.path.exists(TELEMETRY_FILE):
            return "Esperando entrenamiento..."

        with open(TELEMETRY_FILE, encoding="utf-8") as file:
            data = json.load(file)

        return f"CPU: {data.get('cpu', 0):.2f}%\n" f"RAM: {data.get('ram_mb', 0):.2f} MB"

    except Exception as exc:
        return f"Error leyendo telemetría: {exc}"


def check_redis_connection() -> str:
    """Check Redis connectivity and return a human-readable status.

    Returns:
        str: Status indicator with emoji (green/red).
    """
    hm = _get_hm()
    if hm is None:
        return "🔴 Redis ERROR — offline"
    try:
        hm.exist(_HASH_KEY)
        return "🟢 Redis OK"
    except Exception:
        return "🔴 Redis ERROR — offline"


def get_template_from_redis(template_type: str, default_content: str) -> str:
    """Fetch template from central Redis, or initialize it with default if it doesn't exist."""
    hm = _get_hm()
    if hm is None:
        return default_content
    try:
        raw = hm.read_hash(hash_name="invoker:shared_templates", key=template_type)
        if raw is None or not str(raw).strip():
            hm.create_hash(hash_name="invoker:shared_templates", key=template_type, value=default_content)
            return default_content
        return str(raw)
    except Exception:
        return default_content


def load_template() -> str:
    """Load the last saved template from the Redis hash.

    Supports both formats: a dict (new — ``wredis`` auto-deserialises from
    JSON) or a raw YAML/JSON string (legacy).  Returns YAML for the editor.

    Returns:
        str: The YAML content string, or default classification template on fallback.
    """
    hm = _get_hm()
    if hm is None:
        return get_template_from_redis("classification", _TEMPLATE_CLS)
    try:
        raw = hm.read_hash(hash_name=_HASH_KEY, key="template")
        if raw is None:
            return get_template_from_redis("classification", _TEMPLATE_CLS)

        # new format — already a dict
        if isinstance(raw, dict):
            if raw:
                return yaml.dump(raw, default_flow_style=False, allow_unicode=True)
            return get_template_from_redis("classification", _TEMPLATE_CLS)

        # legacy format — stored as a string
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return yaml.dump(parsed, default_flow_style=False, allow_unicode=True)
            except json.JSONDecodeError:
                pass
            # maybe it's a raw YAML string (even older format)
            return raw

        return get_template_from_redis("classification", _TEMPLATE_CLS)
    except Exception:
        return get_template_from_redis("classification", _TEMPLATE_CLS)


def save_template(content: str) -> str | None:
    """Parse YAML and store the resulting dict directly in the Redis hash.

    ``wredis`` serialises the dict as JSON internally, so on read-back
    ``load_template`` receives a dict without extra parsing.

    Args:
        content: The raw YAML string from the editor.

    Returns:
        str | None: A status message if an error occurred, else None.
    """
    hm = _get_hm()
    if hm is None:
        return "🔴 Redis offline — could not save"
    try:
        config_dict = yaml.safe_load(content)
        if not isinstance(config_dict, dict):
            config_dict = {}
        hm.create_hash(hash_name=_HASH_KEY, key="template", value=config_dict)
    except yaml.YAMLError as exc:
        return f"🔴 YAML parse error: {exc}"
    except Exception as exc:
        return f"🔴 Redis error: {exc}"
    return None


def _save_with_feedback(content: str) -> str:
    """Wrap ``save_template`` with a user-facing status message."""
    err = save_template(content)
    if err:
        return err
    return f"🟢 Template saved → `{_HASH_KEY}`"


# ── YAML handling ──────────────────────────────────────────────────


def parse_yaml_file(file: gr.File | None) -> str:
    """Read an uploaded YAML file, validate, persist to Redis, return content.

    Args:
        file: The uploaded file object from Gradio.

    Returns:
        str: The validated YAML content, or an error message prefixed
            with ``"Error reading YAML:"``.
    """
    if file is None:
        return load_template()
    try:
        with open(file.name, encoding="utf-8") as f:  # noqa: PTH123
            content = f.read()
        yaml.safe_load(content)
        save_template(content)
        return content
    except Exception as exc:
        return f"Error reading YAML: {exc}"


# ── Queue resolution ────────────────────────────────────────────────


# def resolve_queue(queue_val: str, custom_val: str) -> str:
#     """Resolve the effective queue name from the UI selector.

#     Args:
#         queue_val: The dropdown selection value.
#         custom_val: The custom queue textbox value (used when
#             ``queue_val == "__custom__"``).

#     Returns:
#         str: The resolved queue name.
#     """
#     if queue_val == "__custom__":
#         return custom_val.strip() or "gpus_high"
#     return queue_val


# ── Task submission ─────────────────────────────────────────────────


def validate_and_launch(
    yaml_content: str,
    execution_mode: str,
) -> str:
    """Validate YAML, persist it, and send a Celery task.

    Args:
        yaml_content: The YAML string from the editor.
        queue_val: Queue dropdown selection.
        custom_val: Custom queue textbox value.

    Returns:
        str: A formatted result message with emoji indicators.
    """
    valid, msg = validate_min_config(yaml_content)
    if not valid:
        return msg or "❌ Configuración inválida"

    save_template(yaml_content)
    queue = _PRIVATE_QUEUE

    try:
        payload: dict[str, Any] = yaml.safe_load(yaml_content)
    except yaml.YAMLError as exc:
        return f"❌ YAML syntax error: {exc}"

    if "user_id" not in payload:
        payload["user_id"] = payload.get("metadata", {}).get("author", "unknown_user")

    try:
        task_name = (
            "tasks.train_on_gpu" if execution_mode == "full" else "tasks.train_on_gpu_simple"
        )

        result = _celery_app.send_task(
            task_name,
            args=[payload],
            queue=queue,
        )

    except Exception as exc:
        return f"❌ Celery error: {exc}"

    model_name = payload.get("model", "?")
    type_name = payload.get("type", "?")
    return (
        "✅ **Training sent**\n\n"
        f"📋 **Task ID:** `{result.id}`\n"
        f"⚙️ **Mode:** `{execution_mode}`\n"
        f"🎯 **Queue:** `{queue}`\n"
        f"📦 **Model:** `{model_name}`\n"
        f"🏷️ **Type:** `{type_name}`"
    )


def check_task_status(task_id: str) -> tuple[str, str]:
    """
    Check the status of a Celery task.

    Args:
        task_id: Celery task identifier.

    Returns:
        Tuple containing:
            - Human-readable task status.
            - LLM analysis text (if available).
    """
    if not task_id.strip():
        return "❌ Task ID required", ""

    try:
        result = AsyncResult(task_id, app=_celery_app)

        info = result.info

        message = f"📋 Task ID: `{task_id}`\n\n" f"📡 State: **{result.state}**\n\n"

        llm_text = ""

        if isinstance(info, dict):

            # Extract LLM report separately
            llm_text = (
                info.get("llm_report") or info.get("llm_analysis") or info.get("analysis") or ""
            )

            # Remove LLM content from the info block
            info_clean = dict(info)
            info_clean.pop("llm_report", None)
            info_clean.pop("llm_analysis", None)
            info_clean.pop("analysis", None)

            for key in [
                "cpu",
                "ram",
                "gpu",
                "epoch",
                "cpu_percent",
                "ram_percent",
                "gpu_percent",
            ]:
                info_clean.pop(key, None)

            if info_clean:
                message += f"ℹ️ Info: `{info_clean}`"

        else:
            message += f"ℹ️ Info: `{info}`"

        return message, llm_text

    except Exception as exc:
        return f"❌ Error: {exc}", ""


def get_executor_stats() -> str:
    """
    Read executor telemetry written by RunTraining.
    """

    telemetry_file = "/results/telemetry.json"

    if not os.path.exists(telemetry_file):
        return "⚪ Waiting for executor telemetry..."

    try:
        with open(telemetry_file, encoding="utf-8") as file:
            telemetry = json.load(file)

        status = telemetry.get("status", "unknown")

        if status != "running":
            return build_status_table(
                epoch="-",
                cpu="-",
                ram="-",
                gpu="-",
            )

        cpu = telemetry.get("cpu", 0)
        ram = telemetry.get("ram_mb", 0)
        gpu = telemetry.get("gpu", 0)
        epoch = telemetry.get("epoch", "N/A")

        return build_status_table(
            epoch=epoch,
            cpu=f"{cpu:.2f}",
            ram=f"{ram:.2f}",
            gpu=gpu,
        )

    except Exception as exc:
        return f"❌ Telemetry error: {exc}"


def get_training_artifacts():

    print("GET TRAINING ARTIFACTS")

    print(_RESULTS_IMAGE)
    print(os.path.exists(_RESULTS_IMAGE))

    print(_CONFUSION_MATRIX_IMAGE)
    print(os.path.exists(_CONFUSION_MATRIX_IMAGE))

    return (
        _RESULTS_IMAGE if os.path.exists(_RESULTS_IMAGE) else None,
        _CONFUSION_MATRIX_IMAGE if os.path.exists(_CONFUSION_MATRIX_IMAGE) else None,
    )


def launch_dry_run() -> str:
    """Send a hardcoded dry-run smoke test directly to the invoker.

    This bypasses the editor content entirely and injects a minimal
    config with ``dry_run: true`` so the invoker simulates training
    without Docker/GPU.

    Returns:
        str: A formatted result message.
    """
    payload: dict[str, Any] = {
        "model": "yolov8n-cls.pt",
        "type": "yolo",
        "dry_run": True,
        "train": {
            "batch": -1,
            "data": "/datasets/examples/classification/colorball.v8i.multiclass/",
            "epochs": 1,
            "imgsz": 640,
        },
        "sweeper": {
            "study_name": f"smoke_test_{_PRIVATE_QUEUE}",
            "fitness": "metrics/accuracy_top1",
        },
        "metadata": {
            "author": "Smoke Test",
            "content": "Dry-run smoke test from Invoker Launcher",
        },
    }

    try:
        result = _celery_app.send_task(
            "tasks.train_on_gpu_simple",
            args=[payload],
            queue=_PRIVATE_QUEUE,
        )
    except Exception as exc:
        return f"❌ Celery error: {exc}"

    return (
        "🧪 **Dry run completed**\n\n"
        f"📋 **Task ID:** `{result.id}`\n"
        f"🎯 **Queue:** `{_PRIVATE_QUEUE}` (private)\n"
        f"📦 **Model:** `yolov8n-cls.pt`\n"
        f"🧪 **Mode:** `dry_run (smoke test)`"
    )


# ── Executor direct run ──────────────────────────────────────────────


def launch_via_executor(yaml_content: str) -> str:
    """Write config to /home/wyolo/request and launch executor container.

    This bypasses the Celery queue entirely, mimicking ``micro_train.sh``:
    writes the YAML to the shared request directory, then runs the
    executor Docker image with GPU access, CIFS mounts, and proper env.
    """
    # 1) Validate config first
    valid, msg = validate_min_config(yaml_content)
    if not valid:
        return msg or "❌ Configuración inválida"

    # 2) Persist to Redis (so it survives reloads)
    save_template(yaml_content)

    # 3) Write to shared request directory for executor to pick up
    request_path = os.path.join(_REQUEST_DIR, "config_train.yaml")
    try:
        os.makedirs(_REQUEST_DIR, exist_ok=True)
        with open(request_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)
    except Exception as exc:
        return f"❌ Failed to write request file: {exc}"

    # 4) Build docker run command (matching micro_train.sh)
    cmd = [
        "docker",
        "run",
        "--rm",
        "--name",
        f"wyolo_executor_{_PRIVATE_QUEUE}",
        "--privileged",
        "--network",
        "host",
        "--shm-size=16g",
        "--cpus=8",
        "--memory=24g",
        "--cap-add=SYS_ADMIN",
        "--cap-add=DAC_READ_SEARCH",
        "--cap-add=NET_ADMIN",
        "--cap-add=SYS_RESOURCE",
        "--gpus",
        "device=0",
        "-e",
        "NVIDIA_VISIBLE_DEVICES=0",
        "-e",
        "NVIDIA_DRIVER_CAPABILITIES=all",
        "-e",
        "TZ=Europe/Madrid",
        "-e",
        "PYTHONUNBUFFERED=1",
        "-e",
        f"CONTROL_HOST={_CONTROL_HOST}",
        "-e",
        "CIFS_USER=wisrovi",
        "-e",
        "CIFS_PASS=wyoloservice",
        "-v",
        "/home/wyolo/events:/wyolo/worker/events:rw",
        "-v",
        "/home/wyolo/train_service_results:/wyolo/worker/train_service_results:rw",
        "-v",
        "/home/wyolo/request:/wyolo/worker/request:rw",
        _EXECUTOR_IMAGE,
        "bash",
        "-c",
        'nvidia-smi && echo "[EXECUTOR] Starting mount..." '
        "&& /usr/local/bin/mount-cifs.sh "
        '&& echo "[EXECUTOR] Mount OK. Starting training..." '
        "&& python main.py --file /wyolo/worker/request/config_train.yaml",
    ]

    try:
        # Run in background (detached) so the UI doesn't block
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return (
            "🚀 **Executor launched**\n\n"
            f"📁 Config written to: `{request_path}`\n"
            f"🐳 Container: `wyolo_executor_{_PRIVATE_QUEUE}`\n"
            f"🔍 Monitor logs with: `docker logs -f wyolo_executor_{_PRIVATE_QUEUE}`\n"
            f"📊 Results in: `/home/wyolo/train_service_results`"
        )
    except FileNotFoundError:
        return "❌ Docker not found. Is Docker installed and running?"
    except Exception as exc:
        return f"❌ Failed to launch executor: {exc}"


# ── Config validation ──────────────────────────────────────────────

_MIN_REQUIRED_KEYS: dict[str, type] = {
    "model": str,
    "type": str,
    "train": dict,
    "metadata": dict,
    "sweeper": dict,
}

_MIN_NESTED: dict[str, dict[str, Any]] = {
    "metadata": {"author": str},
    "sweeper": {"fitness": str, "study_name": str},
}


def validate_min_config(yaml_content: str) -> tuple[bool, str]:
    """Check that the YAML contains all keys needed for a viable training run.

    Returns:
        Tuple of ``(is_valid, message_or_empty)``.
    """
    if not yaml_content.strip():
        return False, ""
    try:
        cfg: Any = yaml.safe_load(yaml_content)
    except yaml.YAMLError:
        return False, ""
    if not isinstance(cfg, dict):
        return False, ""

    for key, expected in _MIN_REQUIRED_KEYS.items():
        if key not in cfg:
            return False, f"❌ Missing required key: *{key}*"
        val = cfg[key]
        if not isinstance(val, expected):
            return False, f"❌ *{key}* debe ser un ``{expected.__name__}``"
        if expected is dict and not val:
            return False, f"❌ *{key}* no puede estar vacío"

    for parent, children in _MIN_NESTED.items():
        for key, expected in children.items():
            if key not in cfg.get(parent, {}):
                return False, f"❌ Missing *{parent}.{key}*"
            val = cfg[parent][key]
            if not isinstance(val, expected):
                if isinstance(expected, tuple):
                    expected_name = " or ".join(t.__name__ for t in expected)
                else:
                    expected_name = expected.__name__

                return (False, f"❌ *{parent}.{key}* debe ser {expected_name}")
                if expected is str and not val.strip():
                    return False, f"❌ *{parent}.{key}* no puede estar vacío"

    train_cfg = cfg.get("train", {})

    if "epochs" in train_cfg and train_cfg["epochs"] <= 0:
        return False, "❌ train.epochs must be > 0"

    if "imgsz" in train_cfg and train_cfg["imgsz"] <= 0:
        return False, "❌ train.imgsz must be > 0"

    if "batch" in train_cfg and train_cfg["batch"] == 0:
        return False, "❌ train.batch cannot be 0"
    if "data" in train_cfg:
        if not train_cfg["data"].strip():
            return False, "❌ train.data cannot be empty"

    return True, "✅ Configuración mínima válida"


def _validate_and_update_btn(yaml_content: str) -> tuple[str, dict]:
    """Validate config and return (message, button-update)."""
    valid, msg = validate_min_config(yaml_content)
    return msg, gr.update(interactive=valid)


# def toggle_custom(queue_val: str) -> dict:
#     """Show or hide the custom queue textbox based on dropdown selection.

#     Args:
#         queue_val: The current dropdown value.

#     Returns:
#         dict: An ``gr.update`` dictionary for the textbox visibility.
#     """
#     return gr.update(visible=(queue_val == "__custom__"))


# ── YAML template reference (shown in the accordion) ────────────────

_YAML_TEMPLATE_DOC: str = """\
```yaml
model: "yolov8n.pt"          # Path or name of the model
type: "yolo"                  # Framework type (e.g. "yolo")
train:
  batch: -1                   # Batch size (-1 = auto)
  data: "/path/to/data"       # Dataset path
  epochs: 2                   # Number of epochs
  imgsz: 640                  # Image size
sweeper:
  study_name: "my_study"      # Optuna study name
  fitness: "metrics/mAP50-95(B)"  # Metric to optimise
metadata:
  author: "Your Name"         # User identifier
  content: "Experiment desc"  # Experiment description
```"""


# ── Quick templates (internal) ──────────────────────────────────────

_TEMPLATE_CLS: str = """model: "yolov8n-cls.pt"
type: "yolo"
train:
  data: "/datasets/clasification/colorball.v8i.multiclass/"
  epochs: 2
  imgsz: 640
sweeper:
  version: 1
  algorithm: optuna
  direction: maximize
  study_name: "color_ball_v2"
  tune: true
  sampler: "TPESampler"
  n_trials: 1
  search_space:
    model: [ "choice", "yolov8n-cls.pt" ]
    train:
      imgsz: [ "choice", 416 ]
      lr0: [ "loguniform", 1e-5, 1e-2 ]
extras:
  gpu:
    id: 0
    limit: 0.95
metadata:
  content: "Este es un experimento de clasificación de imágenes."
  author: "William Rodriguez"
  documentation: "Este modelo fue entrenado con datos del 2025."
"""

_TEMPLATE_DET: str = """model: "yolov8n.pt"
type: "yolo"
train:
  batch: -1
  data: "/datasets/detection/Deteksi komponen elektronik.v1i.yolov8/data.yaml"
  epochs: 2
  imgsz: 640
sweeper:
  version: 1
  algorithm: optuna
  direction: maximize
  study_name: "elektronik_v2"
  tune: true
  sampler: "TPESampler"
  n_trials: 1
  search_space:
    model: [ "choice", "yolov8n.pt" ]
    train:
      imgsz: [ "choice", 416 ]
      lr0: [ "loguniform", 1e-5, 1e-2 ]
extras:
  gpu:
    id: 0
    limit: 0.95
metadata:
  content: "Este es un experimento de clasificación de imágenes."
  author: "William Rodriguez"
  documentation: "Este modelo fue entrenado con datos del 2025."
"""

_TEMPLATE_SEG: str = """model: "yolov8n-seg.pt"
type: "yolo"
# dvc_data_path: /datasets/clasificacion/colorball.v8i.multiclass.dvc
train:
  data: "/datasets/segmentation/ArchitecturePlan/data.yaml"
  epochs: 2
  imgsz: 640
sweeper:
  version: 1
  algorithm: optuna
  direction: maximize
  study_name: "ArchitecturePlan"
  sampler: "TPESampler"
  fitness: "metrics/mAP50(M)"
  n_trials: 1
  search_space:
    #model: ["choice", "yolov8n-seg.pt", "yolov8s-seg.pt", "yolov8m-seg.pt"]
    train:
      imgsz: ["choice", 640]
      lr0: ["loguniform", 1e-5, 1e-2]
      momentum: ["range", 0.85, 0.98, 0.01]
      freeze: ["range", 1, 5, 1]
      optimizer: ["choice", SGD, Adam, AdamW, NAdam, RMSProp]
extras:
  gpu:
    id: 0
    limit: 0.60
metadata:
  content: "Este es un entrenamiento de prueba de Wisrovi"
  author: "Manu G"
  documentation: "Este modelo fue entrenado con datos de marzo 2025."
"""


# ── Theme ───────────────────────────────────────────────────────────

_THEME = gr.themes.Soft(
    primary_hue="blue",
    secondary_hue="slate",
    neutral_hue="gray",
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
)


# ── Keyboard shortcuts (JS injected in <head>) ──────────────────────

_JS_SHORTCUTS: str = """\
<script>
document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        var btn = document.getElementById('train-btn');
        if (btn) btn.click();
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        var btn = document.getElementById('save-btn');
        if (btn) btn.click();
    }
});
</script>"""

_CSS_MODERN: str = """\
/* General container & page background styling */
body {
    background-color: #0b0f19 !important;
}

.gradio-container {
    background-color: #0b0f19 !important;
    font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
}

/* Stunning Glassmorphic header */
#app-header {
    background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #9333ea 100%) !important;
    color: white !important;
    padding: 2.5rem 2rem !important;
    margin-bottom: 2rem !important;
    text-align: center !important;
    border-radius: 16px !important;
    box-shadow: 0 10px 30px rgba(124, 58, 237, 0.4) !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
}

#app-header h1 {
    font-size: 2.8rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.05em !important;
    text-shadow: 0 4px 10px rgba(0,0,0,0.2) !important;
    margin-bottom: 0.5rem !important;
}

#app-header p {
    font-size: 1.1rem !important;
    opacity: 0.9 !important;
    font-weight: 500 !important;
}

/* Beautiful custom tabs */
.tabs {
    border-bottom: 2px solid #1e293b !important;
}

.tab-nav button {
    font-weight: 600 !important;
    font-size: 1rem !important;
    padding: 0.75rem 1.5rem !important;
    transition: all 0.3s ease !important;
    color: #94a3b8 !important;
}

.tab-nav button.selected {
    color: #818cf8 !important;
    border-bottom: 3px solid #6366f1 !important;
}

/* Cards & Accordions Glassmorphic design */
.gr-box, .gr-panel, .gr-form, .gr-block, .gr-row, .gr-group {
    background-color: #111827 !important;
    border: 1px solid #1f2937 !important;
    border-radius: 12px !important;
    padding: 1rem !important;
    margin-bottom: 1rem !important;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06) !important;
}

/* Inputs & Textareas styling */
input, textarea, select, .gr-input {
    background-color: #1f2937 !important;
    color: #f3f4f6 !important;
    border: 1px solid #374151 !important;
    border-radius: 8px !important;
    padding: 0.75rem !important;
    font-size: 0.95rem !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}

input:focus, textarea:focus, select:focus {
    border-color: #6366f1 !important;
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.3) !important;
    outline: none !important;
}

/* Neon buttons */
button.primary, #train-btn {
    background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
    color: white !important;
    font-weight: 700 !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.75rem 1.5rem !important;
    font-size: 1.05rem !important;
    cursor: pointer !important;
    transition: all 0.3s ease !important;
    box-shadow: 0 4px 14px rgba(16, 185, 129, 0.4) !important;
}

button.primary:hover, #train-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(16, 185, 129, 0.6) !important;
}

button.secondary, #save-btn, #check-btn, #refresh-btn {
    background: linear-gradient(135deg, #4f46e5 0%, #4338ca 100%) !important;
    color: white !important;
    font-weight: 600 !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.75rem 1.5rem !important;
    font-size: 1rem !important;
    transition: all 0.3s ease !important;
    box-shadow: 0 4px 14px rgba(79, 70, 229, 0.4) !important;
}

button.secondary:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(79, 70, 229, 0.6) !important;
}

/* Accordions modern design */
details.gr-accordion {
    border: 1px solid #1f2937 !important;
    background-color: #111827 !important;
    border-radius: 12px !important;
    margin-bottom: 1rem !important;
}

details.gr-accordion summary {
    font-weight: 700 !important;
    color: #e5e7eb !important;
    padding: 1rem !important;
    font-size: 1.1rem !important;
    border-bottom: 1px solid #1f2937 !important;
    cursor: pointer !important;
}

/* Optuna and Telemetry Markdown tables styling */
table {
    width: 100% !important;
    border-collapse: collapse !important;
    margin: 1.5rem 0 !important;
    font-size: 0.95rem !important;
    color: #d1d5db !important;
}

th {
    background-color: #1f2937 !important;
    color: #f3f4f6 !important;
    font-weight: 700 !important;
    text-align: left !important;
    padding: 0.75rem 1rem !important;
    border-bottom: 2px solid #374151 !important;
}

td {
    padding: 0.75rem 1rem !important;
    border-bottom: 1px solid #1f2937 !important;
}

tr:nth-child(even) {
    background-color: #111827 !important;
}

tr:hover {
    background-color: #1f2937 !important;
}

#quick-templates-bar {
    justify-content: flex-end;
    gap: 5px;
}

/* Semi-hidden dry-run button */
#dry-run-btn {
    opacity: 0.15 !important;
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    padding: 0 4px !important;
    font-size: 0.8rem !important;
    min-width: 20px !important;
    width: 20px !important;
    transition: opacity 0.2s ease !important;
}
#dry-run-btn:hover { opacity: 0.6 !important; }
"""

_CSS_HIDDEN_DRY_RUN: str = """\
#dry-run-btn {
    opacity: 0.15 !important;
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    padding: 0 4px !important;
    font-size: 0.8rem !important;
    min-width: 20px !important;
    width: 20px !important;
    transition: opacity 0.2s ease !important;
}
#dry-run-btn:hover { opacity: 0.6 !important; }
"""


# ── UI construction ─────────────────────────────────────────────────

with gr.Blocks(title="Invoker Launcher", theme=_THEME, css=_CSS_MODERN) as demo:
    status_timer = gr.Timer(2)
    # dashboard_timer = gr.Timer(10)

    gr.HTML(
        f"""
    <div id="app-header">
        <h1>🚀 Invoker Launcher <span style="font-size: 1.2rem; opacity: 0.7; font-weight: 400;">(Gradio UI {GRADIO_VERSION})</span></h1>
        <p>
            Direct training submission to local GPU invoker • 
            Redis-persisted configs • 
            Queue-aware dispatch
        </p>
    </div>
    <div style="background: rgba(30, 41, 59, 0.7); border: 2px solid #3b82f6; border-radius: 12px; padding: 1.2rem 1rem; margin-bottom: 1.5rem; text-align: center; box-shadow: 0 4px 20px rgba(59, 130, 246, 0.15);">
        <span style="font-size: 1.1rem; color: #94a3b8; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">🎯 Active Destination Queue (Cola Destino):</span>
        <span style="font-size: 1.8rem; color: #60a5fa; font-weight: 900; margin-left: 0.75rem; text-shadow: 0 0 10px rgba(96, 165, 250, 0.5); font-family: monospace;">{_PRIVATE_QUEUE}</span>
    </div>
    """
    )

    status_bar = gr.Markdown(check_redis_connection)

    with gr.Tabs():

        # ============================================================
        # TRAINING TAB
        # ============================================================

        with gr.Tab("🚀 Training"):

            with gr.Row():
                mode_radio = gr.Radio(
                    choices=[("✏️ Edit YAML", "edit"), ("📤 Upload .yaml", "upload")],
                    value="edit",
                    label="Configuration Mode",
                    elem_classes=["mode-selector"],
                    container=False,
                )

            with gr.Column(visible=True) as editor_col:
                with gr.Group(elem_classes=["mode-card"]):
                    with gr.Row():
                        gr.Markdown("### 📄 YAML Configuration")
                        with gr.Row(elem_id="quick-templates-bar"):
                            btn_cls = gr.Button("🟢 Classification", size="sm", variant="secondary")
                            btn_det = gr.Button("🔵 Detection", size="sm", variant="secondary")
                            btn_seg = gr.Button("🔴 Segmentation", size="sm", variant="secondary")

                    yaml_editor = gr.Code(
                        value=load_template,
                        label="YAML Editor",
                        language="yaml",
                        lines=22,
                        interactive=True,
                        elem_id="yaml-editor",
                    )

                    with gr.Row():
                        save_btn = gr.Button(
                            "💾 Save Template",
                            variant="secondary",
                            size="sm",
                            elem_id="save-btn",
                        )

                        clear_btn = gr.Button(
                            "🗑 Clear",
                            variant="secondary",
                            size="sm",
                        )

            with gr.Column(visible=False) as upload_col:
                with gr.Group(elem_classes=["mode-card"]):

                    gr.Markdown("### 📤 Upload YAML Configuration")

                    yaml_file = gr.File(
                        label="Select .yaml / .yml file",
                        file_types=[".yaml", ".yml"],
                        file_count="single",
                        elem_id="yaml-upload",
                    )

                    upload_preview = gr.Code(
                        label="Preview",
                        language="yaml",
                        lines=12,
                        interactive=False,
                        elem_id="upload-preview",
                    )

            with gr.Group(elem_classes=["mode-card"]):

                gr.Markdown("### ⚙️ Dispatch Parameters")

                execution_mode = gr.Radio(
                    choices=[
                        ("⚡ Simple Training", "simple"),
                        ("🔬 Full Pipeline", "full"),
                    ],
                    value="simple",
                    label="Execution Mode",
                )

                gr.Markdown(
                    """
                    💡 **⚡ Simple Training** (tasks.train_on_gpu_simple): Executes the GPU training loop directly, bypassing Samba network mounts and pre-processing pipeline checks.
                    
                    💡 **🔬 Full Pipeline** (tasks.train_on_gpu): Executes the complete MLOps pipeline, including datasets mounting, folder verification, post-training LLM reports, and Optuna registration.
                    """
                )

                output_msg = gr.Markdown("")

                with gr.Row():
                    launch_btn = gr.Button(
                        "🔥 Train",
                        variant="primary",
                        size="lg",
                        interactive=False,
                        elem_id="train-btn",
                    )

                    dry_run_btn = gr.Button(
                        "🧪",
                        variant="secondary",
                        size="sm",
                        elem_id="dry-run-btn",
                    )



        # ============================================================
        # MONITORING TAB
        # ============================================================

        with gr.Tab("📊 Monitoring"):

            hardware_output = gr.Markdown(build_status_table("-", "-", "-", "-"))

            task_id_box = gr.Textbox(
                label="Task ID",
                interactive=True,
                placeholder="Paste task id here...",
            )

            with gr.Row():
                check_btn = gr.Button(
                    "🔍 Check Status",
                    variant="secondary",
                    size="sm",
                )

                refresh_results_btn = gr.Button(
                    "🔄 Refresh Results",
                    size="sm",
                )

            status_output = gr.Markdown("")

            llm_output = gr.Textbox(
                label="LLM Analysis",
                lines=15,
                interactive=False,
            )

            with gr.Accordion(
                "📈 Training Results",
                open=True,
            ):
                with gr.Row():
                    results_plot = gr.Image(label="Training Metrics")

                    confusion_matrix_plot = gr.Image(label="Confusion Matrix")

            with gr.Accordion(
                "🖥️ Local Worker Status",
                open=True
            ):
                local_worker_stats = gr.Markdown()
                refresh_worker_btn = gr.Button("🔄 Refresh Worker Status")

            with gr.Accordion(
                "📊 Optuna Study History",
                open=True
            ):
                with gr.Row():
                    study_selector = gr.Dropdown(
                        choices=list_optuna_studies(),
                        label="Select Study from DB",
                        interactive=True,
                        allow_custom_value=True,
                    )
                    refresh_studies_btn = gr.Button("🔄 Reload Studies List", scale=0)
                
                study_history_output = gr.Markdown("Select a study above to load history.")
                refresh_history_btn = gr.Button("🔄 Refresh Study History")

            with gr.Group(
                elem_id="executor-section",
                visible=True,
            ):
                gr.Markdown("### ⚡ Advanced: Direct Executor Run")

                gr.Markdown(
                    "*Bypasses Celery queue. Writes config to "
                    "`/home/wyolo/request` and launches executor "
                    "container directly with GPU access.*"
                )

                executor_btn = gr.Button(
                    "🚀 Run via Executor",
                    variant="primary",
                    size="lg",
                    elem_id="executor-btn",
                )

                executor_output = gr.Markdown("")

    # -- Event wiring --------------------------------------------------

    # Mode toggle: show/hide editor vs upload
    def _toggle_mode(mode: str):
        return (
            gr.update(visible=mode == "edit"),
            gr.update(visible=mode == "upload"),
        )

    mode_radio.change(
        fn=_toggle_mode,
        inputs=[mode_radio],
        outputs=[editor_col, upload_col],
    )

    # File upload → preview + editor (switches to edit mode)
    def _handle_upload(file: gr.File | None):
        if file is None:
            return gr.update(value=""), gr.update(visible=False), gr.update(visible=True)
        try:
            with open(file.name, encoding="utf-8") as f:
                content = f.read()
            yaml.safe_load(content)  # validate
            save_template(content)
            # Switch to edit mode with loaded content
            return (
                gr.update(value=content),
                gr.update(visible=False),
                gr.update(visible=True),
            )
        except Exception as exc:
            return (
                gr.update(value=f"Error: {exc}"),
                gr.update(visible=True),
                gr.update(visible=False),
            )

    yaml_file.change(
        fn=_handle_upload,
        inputs=[yaml_file],
        outputs=[yaml_editor, upload_col, editor_col],
    )
    yaml_file.change(
        fn=_validate_and_update_btn,
        inputs=[yaml_editor],
        outputs=[output_msg, launch_btn],
    )

    # Editor changes → validate & update train button
    yaml_editor.change(
        fn=_validate_and_update_btn,
        inputs=[yaml_editor],
        outputs=[output_msg, launch_btn],
    )

    save_btn.click(
        fn=_save_with_feedback,
        inputs=[yaml_editor],
        outputs=[status_bar],
    )
    clear_btn.click(
        fn=lambda: ("", gr.update(interactive=False)),
        outputs=[output_msg, launch_btn],
    )

    # queue_selector.change(
    #     fn=toggle_custom,
    #     inputs=[queue_selector],
    #     outputs=[custom_queue],
    # )

    launch_btn.click(
        fn=validate_and_launch,
        inputs=[yaml_editor, execution_mode],
        outputs=[output_msg],
    )
    dry_run_btn.click(fn=launch_dry_run, outputs=[output_msg])

    check_btn.click(
        fn=check_task_status,
        inputs=[task_id_box],
        outputs=[
            status_output,
            llm_output,
        ],
    )

    status_timer.tick(
        fn=check_task_status,
        inputs=[task_id_box],
        outputs=[
            status_output,
            llm_output,
        ],
    )

    status_timer.tick(
        fn=get_executor_stats,
        outputs=[hardware_output],
    )

    status_timer.tick(
        fn=get_local_worker_status,
        outputs=[local_worker_stats],
    )

    refresh_results_btn.click(
        fn=get_training_artifacts,
        outputs=[
            results_plot,
            confusion_matrix_plot,
        ],
    )

    btn_cls.click(
        fn=lambda: get_template_from_redis("classification", _TEMPLATE_CLS),
        outputs=[yaml_editor],
    )

    btn_det.click(
        fn=lambda: get_template_from_redis("detection", _TEMPLATE_DET),
        outputs=[yaml_editor],
    )

    btn_seg.click(
        fn=lambda: get_template_from_redis("segmentation", _TEMPLATE_SEG),
        outputs=[yaml_editor],
    )

    refresh_worker_btn.click(
        fn=get_local_worker_status,
        outputs=[local_worker_stats],
    )

    refresh_studies_btn.click(
        fn=lambda: gr.update(choices=list_optuna_studies()),
        outputs=[study_selector],
    )

    refresh_history_btn.click(
        fn=get_optuna_study_history,
        inputs=[study_selector],
        outputs=[study_history_output],
    )

    # Automatically load worker status on page load
    demo.load(
        fn=get_local_worker_status,
        outputs=[local_worker_stats],
    )

    # Executor direct run
    executor_btn.click(
        fn=launch_via_executor,
        inputs=[yaml_editor],
        outputs=[executor_output],
    )


# ── Entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    demo.launch(  # noqa: S104
        server_name="0.0.0.0",
        server_port=7860,
        # theme=_THEME,
        head=_JS_SHORTCUTS,
        # css=_CSS_HIDDEN_DRY_RUN,
        allowed_paths=["/results"],
    )
