import os

import yaml
from celery import Celery
from wredis import RedisHashManager

# Constants & Env vars
_CONTROL_HOST = os.getenv("CONTROL_HOST", "127.0.0.1")
_REDIS_PORT = 23_437
_REDIS_URL = f"redis://{_CONTROL_HOST}:{_REDIS_PORT}/0"

GRADIO_VERSION = "v1.2.2"

_PRIVATE_QUEUE = os.getenv("PRIVATE_QUEUE") or os.getenv("WORKER_HOST") or "default"
if _PRIVATE_QUEUE == "default" and os.getenv("WORKER_HOST"):
    _PRIVATE_QUEUE = os.getenv("WORKER_HOST")

_HASH_KEY = f"invoker:{_PRIVATE_QUEUE}:template_invoker"

# Initialize Celery
_celery_app = Celery(
    "invoker_launcher",
    broker=_REDIS_URL,
    backend=_REDIS_URL,
)

# Execution mode comes from config.yaml (not from the UI)
from config import load_ui_config  # noqa: E402

RUN_FULL_PIPELINE: bool = bool(load_ui_config().get("run_full_pipeline", True))

_hm = None

def _get_hm() -> RedisHashManager | None:
    """Lazy-init and return the RedisHashManager singleton."""
    global _hm
    if _hm is None:
        try:
            _hm = RedisHashManager(host=_CONTROL_HOST, port=_REDIS_PORT)
        except Exception:
            return None
    return _hm

def check_redis_connection() -> str:
    """Check connection to central Redis container."""
    hm = _get_hm()
    if hm is None:
        return "🔴 Redis ERROR — offline"
    try:
        hm.exist(_HASH_KEY)
        return "🟢 Redis OK"
    except Exception:
        return "🔴 Redis ERROR — offline"

def get_local_worker_status() -> str:
    """Query Celery active tasks and status of the local worker node.

    This is an *advanced* diagnostic: it tells you whether the local Celery
    daemon is alive, how many tasks it can run at once (concurrency), which
    tasks are currently executing on this node, and which are still waiting
    in the queue. Normal users can ignore it — it is shown here so operators
    can verify the node is healthy.
    """
    try:
        worker_name = f"celery@wyolo_invoker_{_PRIVATE_QUEUE}"
        inspect = _celery_app.control.inspect([worker_name])

        # Ping the worker
        ping = inspect.ping()
        if not ping or worker_name not in ping:
            return (
                "### 🖥️ Local Worker Status *(diagnóstico)*\n\n"
                "🔴 **Status:** Offline / Disconnected\n\n"
                f"🎯 **Queue Target:** `{_PRIVATE_QUEUE}`\n\n"
                "⚠️ *Verify that the Celery worker container is running on this host.*\n\n"
                "---\n"
                "*💡 **¿Para qué sirve esto?** Comprueba que el daemon Celery de este nodo "
                "está vivo y escuchando. Si aparece offline, ningún entrenamiento "
                "llegará a esta máquina.*"
            )

        # Get active tasks
        active = inspect.active()
        active_tasks = active.get(worker_name, []) if active else []

        # Get stats (concurrency, etc)
        stats = inspect.stats()
        concurrency = "-"
        if stats and worker_name in stats:
            concurrency = stats[worker_name].get("pool", {}).get("max-concurrency", "-")

        # Format markdown response
        status_md = "### 🖥️ Local Worker Status *(diagnóstico)*\n\n"
        status_md += "🟢 **Status:** Online &nbsp;&nbsp;|\u00a0\u00a0 "
        status_md += (
            f"🎯 **Queue Target:** `{_PRIVATE_QUEUE}` &nbsp;&nbsp;|\u00a0\u00a0 "
            f"🚀 **Concurrency:** {concurrency}\n\n"
        )

        status_md += "#### 🏃 Active Tasks (ejecutándose ahora):\n"
        if not active_tasks:
            status_md += "*Ninguna. Este nodo está libre.*"
        else:
            for task in active_tasks:
                task_id = task.get("id", "unknown")
                name = task.get("name", "unknown")
                args = task.get("args", "")
                status_md += (
                    f"- **Task:** `{name}`\n  - **ID:** `{task_id}`\n  - **Args:** `{args}`\n"
                )

        # Get reserved tasks (in queue)
        reserved = inspect.reserved()
        reserved_tasks = reserved.get(worker_name, []) if reserved else []

        status_md += "\n\n#### 📥 Reserved / Queued Tasks (en cola):\n"
        if not reserved_tasks:
            status_md += "*Ninguna tarea en espera.*"
        else:
            for task in reserved_tasks:
                task_id = task.get("id", "unknown")
                name = task.get("name", "unknown")
                status_md += f"- **Task:** `{name}` (ID: `{task_id}`)\n"

        status_md += (
            "\n---\n"
            "*💡 **¿Para qué sirve esto?** Confirma que este nodo GPU está operativo "
            "(Online), cuántos entrenamientos ejecuta en paralelo (Concurrency = 1 "
            "en producción) y qué tareas maneja. Puedes ignorarlo en uso normal.*"
        )
        return status_md
    except Exception as e:
        return f"⚠️ **Error querying Celery worker:** `{str(e)}`"

def validate_min_config(yaml_content: str) -> tuple[bool, str]:
    """Basic structural validation of the training config before Celery submission."""
    if not yaml_content.strip():
        return False, "❌ YAML configuration is empty"
    try:
        cfg = yaml.safe_load(yaml_content)
    except yaml.YAMLError as ye:
        return False, f"❌ Invalid YAML syntax: {str(ye)}"

    if not isinstance(cfg, dict):
        return False, "❌ YAML must define a key-value mapping structure"

    # Minimal mandatory keys
    if "model" not in cfg:
        return False, "❌ Missing mandatory key: 'model'"
    if "type" not in cfg:
        return False, "❌ Missing mandatory key: 'type'"

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

def validate_and_launch(yaml_content: str) -> str:
    """Validate YAML, persist it locally, and send the corresponding Celery task.

    The execution mode (``tasks.train_on_gpu`` vs ``tasks.train_on_gpu_simple``)
    and the destination queue are controlled by ``config.yaml``, never by the UI.
    """
    from config import RUN_FULL_PIPELINE

    valid, msg = validate_min_config(yaml_content)
    if not valid:
        return msg

    try:
        config_dict = yaml.safe_load(yaml_content)
    except Exception as e:
        return f"❌ Unexpected YAML parse error: {str(e)}"

    # Inject user_id from metadata.author (used for traceability) when absent
    if "user_id" not in config_dict:
        metadata = config_dict.get("metadata") or {}
        config_dict["user_id"] = metadata.get("author", "unknown")

    # Save to Redis
    save_template_ok = False
    hm = _get_hm()
    if hm is not None:
        try:
            hm.create_hash(hash_name=_HASH_KEY, key="template", value=config_dict)
            save_template_ok = True
        except Exception:
            pass

    task_name = "tasks.train_on_gpu" if RUN_FULL_PIPELINE else "tasks.train_on_gpu_simple"
    mode_label = (
        "Full Pipeline (EDA + Optuna + LLM)"
        if RUN_FULL_PIPELINE
        else "Direct Executor Run (simple)"
    )

    try:
        result = _celery_app.send_task(
            task_name,
            args=[config_dict],
            queue=_PRIVATE_QUEUE,
        )
        task_id = result.id
        redis_status = f"saved to `{_HASH_KEY}`" if save_template_ok else "failed to save to Redis"
        return (
            f"🚀 **Training Task Sent!**\n\n"
            f"⚙️ **Mode:** `{mode_label}`\n"
            f"🎯 **Queue:** `{_PRIVATE_QUEUE}`\n"
            f"🆔 **Task ID:** `{task_id}`\n"
            f"📝 **State:** {redis_status}\n\n"
            f"*The Task ID has been copied automatically to the 📊 Monitoring tab — "
            f"status and resources refresh by themselves.*"
        )
    except Exception as e:
        return f"❌ **Failed to send task via Celery:** `{str(e)}`"


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


def launch_dry_run() -> str:
    """Send a hardcoded dry-run smoke test directly to the invoker."""
    payload = {
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
