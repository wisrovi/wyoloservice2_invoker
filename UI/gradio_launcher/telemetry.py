import os
import json
import socket
import shutil
from celery.result import AsyncResult
from celery_client import _celery_app, _PRIVATE_QUEUE, _CONTROL_HOST, validate_min_config

# Telemetry File
TELEMETRY_FILE = "/results/telemetry.json"

_EVALUATION_DIR = "/results/evaluation_metrics"
_RESULTS_IMAGE = os.path.join(_EVALUATION_DIR, "results.png")
_CONFUSION_MATRIX_IMAGE = os.path.join(_EVALUATION_DIR, "confusion_matrix.png")

def get_host_ip() -> str:
    """Get host machine IP from inside Docker."""
    try:
        return socket.gethostbyname("host.docker.internal")
    except Exception:
        return "127.0.0.1"

def build_status_table(epoch, cpu, ram, gpu) -> str:
    return (
        f"🖥️ **CPU:** {cpu}% &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"💾 **RAM:** {ram} MB &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"🎮 **GPU:** {gpu}% &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"🔄 **Epoch:** {epoch}"
    )

def get_telemetry() -> str:
    try:
        if not os.path.exists(TELEMETRY_FILE):
            return "Esperando entrenamiento..."

        with open(TELEMETRY_FILE, encoding="utf-8") as file:
            data = json.load(file)

        return f"CPU: {data.get('cpu', 0):.2f}%\n" f"RAM: {data.get('ram_mb', 0):.2f} MB"
    except Exception as exc:
        return f"Error leyendo telemetría: {exc}"

def get_executor_stats() -> str:
    """Read executor telemetry written by RunTraining."""
    if not os.path.exists(TELEMETRY_FILE):
        return "⚪ Waiting for executor telemetry..."

    try:
        with open(TELEMETRY_FILE, encoding="utf-8") as file:
            telemetry = json.load(file)

        status = telemetry.get("status", "unknown")
        if status != "running":
            return build_status_table(epoch="-", cpu="-", ram="-", gpu="-")

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

def get_training_artifacts() -> tuple[str | None, str | None]:
    return (
        _RESULTS_IMAGE if os.path.exists(_RESULTS_IMAGE) else None,
        _CONFUSION_MATRIX_IMAGE if os.path.exists(_CONFUSION_MATRIX_IMAGE) else None,
    )

def check_task_status(task_id: str) -> tuple[str, str]:
    """Check the status of a Celery task."""
    if not task_id.strip():
        return "❌ Task ID required", "⏳ Awaiting training completion to generate LLM analysis report..."

    try:
        result = AsyncResult(task_id, app=_celery_app)
        info = result.info
        message = f"📋 Task ID: `{task_id}`\n\n📡 State: **{result.state}**\n\n"
        llm_text = ""

        if result.state in ["PENDING", "STARTED", "RETRY"]:
            llm_text = "⏳ Training in progress. LLM analysis report will be generated upon completion..."
        elif result.state == "SUCCESS":
            if isinstance(info, dict):
                llm_text = info.get("llm_report") or info.get("llm_analysis") or info.get("analysis") or "✅ Training succeeded, but no LLM analysis report was found."
            else:
                llm_text = "✅ Training succeeded."
        elif result.state == "FAILURE":
            llm_text = f"❌ Training failed. Info: {info}"
        else:
            llm_text = f"State: {result.state}"

        if isinstance(info, dict):
            # Remove LLM/Telemetry keys from the info block
            info_clean = dict(info)
            info_clean.pop("llm_report", None)
            info_clean.pop("llm_analysis", None)
            info_clean.pop("analysis", None)

            for key in ["cpu", "ram", "gpu", "epoch", "cpu_percent", "ram_percent", "gpu_percent"]:
                info_clean.pop(key, None)

            if info_clean:
                message += f"ℹ️ Info: `{info_clean}`"
        else:
            message += f"ℹ️ Info: `{info}`"

        return message, llm_text
    except Exception as exc:
        return f"❌ Error: {exc}", ""

def get_results_zip() -> str | None:
    """Creates a zip archive of the /results/evaluation_metrics directory and returns its path."""
    zip_base = "/results/evaluation_metrics"
    if not os.path.exists(zip_base):
        return None
    zip_out = "/results/training_results"
    try:
        shutil.make_archive(zip_out, 'zip', zip_base)
        zip_file_path = zip_out + ".zip"
        if os.path.exists(zip_file_path):
            return zip_file_path
    except Exception as e:
        print(f"Error creating zip archive: {e}")
    return None
