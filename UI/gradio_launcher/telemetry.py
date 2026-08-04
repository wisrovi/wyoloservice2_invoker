import os
import json
import socket
import subprocess
from celery.result import AsyncResult
from celery_client import _celery_app, _PRIVATE_QUEUE, _CONTROL_HOST, validate_min_config
from templates import save_template

# Telemetry File
TELEMETRY_FILE = "/results/telemetry.json"

# Constants for Executor
_EXECUTOR_IMAGE = "wisrovi/train_service:worker_executor_v1.0.0"
_REQUEST_DIR = "/home/wyolo/request"
_EVENTS_DIR = "/home/wyolo/events"
_RESULTS_DIR = "/results"
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
        return "❌ Task ID required", ""

    try:
        result = AsyncResult(task_id, app=_celery_app)
        info = result.info
        message = f"📋 Task ID: `{task_id}`\n\n📡 State: **{result.state}**\n\n"
        llm_text = ""

        if isinstance(info, dict):
            # Extract LLM report separately
            llm_text = (
                info.get("llm_report") or info.get("llm_analysis") or info.get("analysis") or ""
            )

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

def launch_via_executor(yaml_content: str) -> str:
    """Write config to /home/wyolo/request and launch executor container in background."""
    valid, msg = validate_min_config(yaml_content)
    if not valid:
        return msg or "❌ Configuración inválida"

    # Persist locally via save_template
    save_template(yaml_content)

    # Write to shared request directory
    request_path = os.path.join(_REQUEST_DIR, "config_train.yaml")
    try:
        os.makedirs(_REQUEST_DIR, exist_ok=True)
        with open(request_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)
    except Exception as exc:
        return f"❌ Failed to write request file: {exc}"

    # Build docker run command
    cmd = [
        "docker", "run", "--rm",
        "--name", f"wyolo_executor_{_PRIVATE_QUEUE}",
        "--privileged",
        "--network", "host",
        "--shm-size=16g",
        "--cpus=8",
        "--memory=24g",
        "--cap-add=SYS_ADMIN",
        "--cap-add=DAC_READ_SEARCH",
        "--cap-add=NET_ADMIN",
        "--cap-add=SYS_RESOURCE",
        "--gpus", "device=0",
        "-e", "NVIDIA_VISIBLE_DEVICES=0",
        "-e", "NVIDIA_DRIVER_CAPABILITIES=all",
        "-e", "TZ=Europe/Madrid",
        "-e", "PYTHONUNBUFFERED=1",
        "-e", f"CONTROL_HOST={_CONTROL_HOST}",
        "-e", "CIFS_USER=wisrovi",
        "-e", "CIFS_PASS=wyoloservice",
        "-v", "/home/wyolo/events:/wyolo/worker/events:rw",
        "-v", "/home/wyolo/train_service_results:/wyolo/worker/train_service_results:rw",
        "-v", "/home/wyolo/request:/wyolo/worker/request:rw",
        _EXECUTOR_IMAGE,
        "bash", "-c",
        'nvidia-smi && echo "[EXECUTOR] Starting mount..." '
        "&& /usr/local/bin/mount-cifs.sh "
        '&& echo "[EXECUTOR] Mount OK. Starting training..." '
        "&& python main.py --file /wyolo/worker/request/config_train.yaml",
    ]

    try:
        subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
