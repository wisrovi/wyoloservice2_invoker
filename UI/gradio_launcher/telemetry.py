import html
import json
import os
import socket
import zipfile

import gradio as gr

from celery.result import AsyncResult

from celery_client import _CONTROL_HOST, _PRIVATE_QUEUE, _celery_app  # noqa: F401
from config import SHOW_NORMALIZED_CONFUSION_MATRIX

# ── Filesystem layout ────────────────────────────────────────────────
RESULTS_DIR = "/results"
TELEMETRY_FILE = os.path.join(RESULTS_DIR, "telemetry.json")
_EVALUATION_DIR = os.path.join(RESULTS_DIR, "evaluation_metrics")
_RESULTS_IMAGE = os.path.join(_EVALUATION_DIR, "results.png")
_CONFUSION_MATRIX_IMAGE = os.path.join(_EVALUATION_DIR, "confusion_matrix.png")
_NORMALIZED_CONFUSION_MATRIX_IMAGE = os.path.join(
    _EVALUATION_DIR, "confusion_matrix_normalized.png"
)
ZIP_PATH = os.path.join(RESULTS_DIR, "training_results.zip")


def get_host_ip() -> str:
    """Get host machine IP from inside Docker."""
    try:
        return socket.gethostbyname("host.docker.internal")
    except Exception:
        return "127.0.0.1"


# ── HTML building blocks ─────────────────────────────────────────────

def _bar(pct: float, color: str = "#10b981") -> str:
    """HTML progress bar. pct is clamped to [0, 100]."""
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        pct = 0.0
    pct = max(0.0, min(100.0, pct))
    return (
        f'<div class="bar"><div class="bar-fill" '
        f'style="width:{pct:.1f}%;background:{color};box-shadow:0 0 8px {color};"></div></div>'
    )


def _res_card(icon: str, label: str, value: str, pct: float | None = None) -> str:
    if pct is not None:
        bar = _bar(pct, _pct_color(pct))
    else:
        bar = ""
    return (
        f'<div class="res-card">'
        f'<div class="res-icon">{icon}</div>'
        f'<div class="res-label">{label}</div>'
        f'<div class="res-value">{value}</div>{bar}'
        f"</div>"
    )


def _pct_color(pct: float) -> str:
    """Green < 60%, amber 60-85%, red above."""
    if pct < 60:
        return "#10b981"
    if pct < 85:
        return "#f59e0b"
    return "#ef4444"


def _render_dashboard(cpu: str, ram: str, gpu: str, epoch: str, running: bool) -> str:
    if not running:
        return (
            '<div class="res-grid">'
            + _res_card("🖥️", "CPU", "—")
            + _res_card("💾", "RAM", "—")
            + _res_card("🎮", "GPU", "—")
            + _res_card("🔄", "Epoch", "—")
            + "</div>"
            '<div class="res-wait">⚪ Waiting for the executor to report resources… '
            "Start a training from the 🚀 Train tab.</div>"
        )
    try:
        cpu_f = float(cpu)
        ram_f = float(ram)
        gpu_f = float(gpu)
        cpu_card = _res_card("🖥️", "CPU", f"{cpu_f:.1f}%", cpu_f)
        ram_card = _res_card("💾", "RAM", f"{ram_f:.0f} MB", ram_f)
        gpu_card = _res_card("🎮", "GPU", f"{gpu_f:.1f}%", gpu_f)
    except (TypeError, ValueError):
        cpu_card = _res_card("🖥️", "CPU", str(cpu))
        ram_card = _res_card("💾", "RAM", str(ram))
        gpu_card = _res_card("🎮", "GPU", str(gpu))
    epoch_card = _res_card("🔄", "Epoch", str(epoch))
    return f'<div class="res-grid">{cpu_card}{ram_card}{gpu_card}{epoch_card}</div>'


def get_executor_stats() -> str:
    """HTML resource dashboard (CPU / RAM / GPU / Epoch) with progress bars."""
    if not os.path.exists(TELEMETRY_FILE):
        return _render_dashboard("-", "-", "-", "-", running=False)
    try:
        with open(TELEMETRY_FILE, encoding="utf-8") as file:
            telemetry = json.load(file)
    except Exception:
        return _render_dashboard("-", "-", "-", "-", running=False)

    running = telemetry.get("status") == "running"
    cpu = telemetry.get("cpu", "-")
    ram = telemetry.get("ram_mb", "-")
    gpu = telemetry.get("gpu", "-")
    epoch = telemetry.get("epoch", "-")
    return _render_dashboard(str(cpu), str(ram), str(gpu), str(epoch), running)


def get_training_artifacts() -> tuple[str | None, str | None]:
    confusion_matrix = (
        _NORMALIZED_CONFUSION_MATRIX_IMAGE
        if SHOW_NORMALIZED_CONFUSION_MATRIX
        else _CONFUSION_MATRIX_IMAGE
    )
    return (
        _RESULTS_IMAGE if os.path.exists(_RESULTS_IMAGE) else None,
        confusion_matrix if os.path.exists(confusion_matrix) else None,
    )


# ── Task status ──────────────────────────────────────────────────────

_STATE_STYLE = {
    "PENDING": ("#f59e0b", "⏳"),
    "STARTED": ("#3b82f6", "🚀"),
    "PROGRESS": ("#3b82f6", "🚀"),
    "RETRY": ("#f59e0b", "🔁"),
    "SUCCESS": ("#10b981", "✅"),
    "FAILURE": ("#ef4444", "❌"),
    "REVOKED": ("#ef4444", "⛔"),
}


def _idle_status() -> str:
    return (
        '<div class="status-card"><div class="status-pill" style="background:#475569;">⚪</div>'
        '<div class="status-body"><div class="status-title">No active task</div>'
        "<div class=\"status-desc\">Launch a training from the 🚀 Train tab — "
        "the Task ID will be tracked here automatically.</div></div></div>"
    )


def _idle_llm() -> str:
    return (
        '<div class="llm-state">⚪ <b>Waiting for a training task…</b><br>'
        "The LLM analysis report will be generated automatically once the "
        "training completes.</div>"
    )


def _task_status_card(task_id: str, state: str, info: dict) -> str:
    color, emoji = _STATE_STYLE.get(state, ("#64748b", "📡"))

    detail_rows = ""
    meta_status = info.get("status") if isinstance(info, dict) else None
    if meta_status:
        detail_rows += f"<div><b>Status:</b> {meta_status}</div>"
    invoker = info.get("invoker") if isinstance(info, dict) else None
    if invoker:
        detail_rows += f"<div><b>Invoker:</b> <code>{invoker}</code></div>"
    epoch = info.get("epoch") if isinstance(info, dict) else None
    if epoch and str(epoch) not in ("N/A", ""):
        detail_rows += f"<div><b>Epoch:</b> {epoch}</div>"
    if state == "SUCCESS" and isinstance(info, dict):
        acc = info.get("accuracy")
        if acc is not None:
            detail_rows += f"<div><b>Accuracy:</b> <code>{acc}</code></div>"

    return (
        f'<div class="status-card">'
        f'<div class="status-pill" style="background:{color};">{emoji}</div>'
        f'<div class="status-body">'
        f'<div class="status-title">State: <b style="color:{color};">{state}</b></div>'
        f"<div>📋 <b>Task ID:</b> <code>{task_id}</code></div>"
        f"{detail_rows}"
        f"</div></div>"
    )


def _llm_status(state: str, info: dict) -> str:
    if state in ("PENDING", "STARTED", "PROGRESS", "RETRY"):
        return (
            '<div class="llm-state">🧠 <b>Training in progress…</b><br>'
            "The LLM analysis report is queued and will be generated automatically "
            "when the training finishes.</div>"
        )
    if state == "SUCCESS":
        report = (
            info.get("llm_report")
            or info.get("llm_analysis")
            or info.get("analysis")
            if isinstance(info, dict)
            else None
        )
        if report:
            return (
                '<div class="llm-state llm-done">✅ <b>LLM Analysis Report</b><br>'
                f'<div class="llm-report">{html.escape(str(report))}</div></div>'
            )
        return (
            '<div class="llm-state llm-done">✅ <b>Training completed.</b><br>'
            "No LLM analysis report was found in the task result.</div>"
        )
    if state == "FAILURE":
        return (
            f'<div class="llm-state llm-error">❌ <b>Training failed.</b><br>'
            f"<code>{html.escape(str(info))}</code></div>"
        )
    return _idle_llm()


def check_task_status(task_id: str | None) -> tuple[str, str]:
    """Check Celery task state and return (status_html, llm_html)."""
    if not task_id or not str(task_id).strip():
        return _idle_status(), _idle_llm()

    try:
        result = AsyncResult(task_id, app=_celery_app)
    except Exception as exc:
        return (
            f'<div class="llm-state llm-error">❌ Error: <code>{exc}</code></div>',
            _idle_llm(),
        )

    state = result.state
    info = result.info if isinstance(result.info, dict) else {}

    # Extract the LLM/analysis keys without mutating the original info dict
    status_html = _task_status_card(task_id, state, info)
    llm_html = _llm_status(state, info)
    return status_html, llm_html


# ── Results download ─────────────────────────────────────────────────

def results_available() -> bool:
    """True when the executor has written any results artifacts."""
    if os.path.exists(os.path.join(RESULTS_DIR, "results.json")):
        return True
    if os.path.isdir(_EVALUATION_DIR):
        try:
            return any(os.scandir(_EVALUATION_DIR))
        except OSError:
            return False
    return False


def get_results_zip() -> str | None:
    """Zip the ENTIRE results directory (weights, metrics, plots, configs)."""
    if not os.path.isdir(RESULTS_DIR):
        return None
    if not results_available():
        return None
    try:
        if os.path.exists(ZIP_PATH):
            os.remove(ZIP_PATH)
        with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(RESULTS_DIR):
                for name in files:
                    fp = os.path.join(root, name)
                    if fp == ZIP_PATH or name.endswith(".zip"):
                        continue
                    zf.write(fp, os.path.relpath(fp, RESULTS_DIR))
        return ZIP_PATH if os.path.exists(ZIP_PATH) else None
    except Exception as exc:
        print(f"Error creating zip archive: {exc}")
        return None
