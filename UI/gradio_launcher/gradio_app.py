# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
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

# ── Constants ──────────────────────────────────────────────────────
_CONTROL_HOST: str = os.getenv("CONTROL_HOST", "127.0.0.1")
_REDIS_PORT: int = 23_437
_REDIS_URL: str = f"redis://{_CONTROL_HOST}:{_REDIS_PORT}/0"

_PRIVATE_QUEUE: str = (
    os.getenv("PRIVATE_QUEUE")
    or os.getenv("WORKER_HOST")
    or subprocess.getoutput("hostname -I").split()[0]
    or "default"
)

_HASH_KEY: str = f"wyolo:invokers:{_PRIVATE_QUEUE}"

_celery_app: Celery = Celery(
    "invoker_launcher",
    broker=_REDIS_URL,
    backend=_REDIS_URL,
)
_hm: RedisHashManager | None = None


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


def load_template() -> str:
    """Load the last saved template from the Redis hash.

    Supports both formats: a dict (new — ``wredis`` auto-deserialises from
    JSON) or a raw YAML/JSON string (legacy).  Returns YAML for the editor.

    Returns:
        str: The YAML content string, or empty string on failure.
    """
    hm = _get_hm()
    if hm is None:
        return ""
    try:
        raw = hm.read_hash(hash_name=_HASH_KEY, key="template")
        if raw is None:
            return ""

        # new format — already a dict
        if isinstance(raw, dict):
            if raw:
                return yaml.dump(raw, default_flow_style=False, allow_unicode=True)
            return ""

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

        return ""
    except Exception:
        return ""


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


def resolve_queue(queue_val: str, custom_val: str) -> str:
    """Resolve the effective queue name from the UI selector.

    Args:
        queue_val: The dropdown selection value.
        custom_val: The custom queue textbox value (used when
            ``queue_val == "__custom__"``).

    Returns:
        str: The resolved queue name.
    """
    if queue_val == "__custom__":
        return custom_val.strip() or "gpus_high"
    return queue_val


# ── Task submission ─────────────────────────────────────────────────


def validate_and_launch(
    yaml_content: str,
    queue_val: str,
    custom_val: str,
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
    queue = resolve_queue(queue_val, custom_val)

    try:
        payload: dict[str, Any] = yaml.safe_load(yaml_content)
    except yaml.YAMLError as exc:
        return f"❌ YAML syntax error: {exc}"

    if "user_id" not in payload:
        payload["user_id"] = payload.get("metadata", {}).get("author", "unknown_user")

    try:
        result = _celery_app.send_task(
            "tasks.train_on_gpu_simple",
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
        f"🎯 **Queue:** `{queue}`\n"
        f"📦 **Model:** `{model_name}`\n"
        f"🏷️ **Type:** `{type_name}`"
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


# ── Config validation ──────────────────────────────────────────────

_MIN_REQUIRED_KEYS: dict[str, type] = {
    "model": str,
    "type": str,
    "train": dict,
    "metadata": dict,
    "sweeper": dict,
}

_MIN_NESTED: dict[str, dict[str, type]] = {
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
                return False, f"❌ *{parent}.{key}* debe ser un ``{expected.__name__}``"
            if expected is str and not val.strip():
                return False, f"❌ *{parent}.{key}* no puede estar vacío"

    return True, "✅ Configuración mínima válida"


def _validate_and_update_btn(yaml_content: str) -> tuple[str, dict]:
    """Validate config and return (message, button-update)."""
    valid, msg = validate_min_config(yaml_content)
    return msg, gr.update(interactive=valid)


def toggle_custom(queue_val: str) -> dict:
    """Show or hide the custom queue textbox based on dropdown selection.

    Args:
        queue_val: The current dropdown value.

    Returns:
        dict: An ``gr.update`` dictionary for the textbox visibility.
    """
    return gr.update(visible=(queue_val == "__custom__"))


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

_TEMPLATE_CLS: str = """\
model: "yolov8n-cls.pt"
type: "yolo"
train:
  batch: -1
  data: "/datasets/examples/classification/colorball.v8i.multiclass/"
  epochs: 2
  imgsz: 640
sweeper:
  study_name: "exp_classification"
  fitness: "metrics/accuracy_top1"
metadata:
  author: "Gradio User"
  content: "Classification experiment"
"""

_TEMPLATE_DET: str = """\
model: "yolov8n.pt"
type: "yolo"
train:
  batch: -1
  data: "/datasets/examples/detection/colorball.v8i.multiclass/"
  epochs: 2
  imgsz: 640
sweeper:
  study_name: "exp_detection"
  fitness: "metrics/mAP50-95(B)"
metadata:
  author: "Gradio User"
  content: "Detection experiment"
"""

_TEMPLATE_SEG: str = """\
model: "yolov8n-seg.pt"
type: "yolo"
train:
  batch: -1
  data: "/datasets/examples/segmentation/ArchitecturePlan/data.yaml"
  epochs: 2
  imgsz: 640
sweeper:
  study_name: "ArchitecturePlan"
  fitness: "metrics/mAP50(M)"
metadata:
  author: "Manu G"
  content: "Segmentation experiment"
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
#dry-run-btn:hover {
    opacity: 0.6 !important;
}
"""


# ── UI construction ─────────────────────────────────────────────────

with gr.Blocks(title="Invoker Launcher") as demo:
    # -- Status bar --------------------------------------------------
    status_bar = gr.Markdown(check_redis_connection)

    # -- Main row ----------------------------------------------------
    with gr.Row():
        # LEFT — YAML editor
        with gr.Column(scale=2):
            gr.Markdown("### 📄 YAML Configuration")
            yaml_file = gr.File(
                label="Upload .yaml file",
                file_types=[".yaml", ".yml"],
            )
            yaml_editor = gr.Code(
                value=load_template,
                label="YAML Editor",
                language="yaml",
                lines=20,
                interactive=True,
            )
            with gr.Row():
                save_btn = gr.Button(
                    "💾 Save",
                    variant="secondary",
                    size="sm",
                    elem_id="save-btn",
                )
                clear_btn = gr.Button(
                    "🗑 Clear",
                    variant="secondary",
                    size="sm",
                )

        # RIGHT — Send parameters
        with gr.Column(scale=1):
            gr.Markdown("### ⚙️ Send Parameters")
            queue_selector = gr.Dropdown(
                choices=[
                    (f"🖥️ Private ({_PRIVATE_QUEUE})", _PRIVATE_QUEUE),
                    ("⚡ High priority (gpus_high)", "gpus_high"),
                    ("✏️ Custom...", "__custom__"),
                ],
                label="Destination Queue",
                value=_PRIVATE_QUEUE,
                info=(
                    "Default: local invoker's private queue. "
                    "High priority routes to any available invoker."
                ),
            )
            custom_queue = gr.Textbox(
                label="Custom Queue Name",
                placeholder="gpus_medium",
                visible=False,
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

    # -- Accordions --------------------------------------------------
    with gr.Accordion("📋 YAML Reference", open=False):
        gr.Markdown(_YAML_TEMPLATE_DOC)

    with gr.Accordion("💡 Quick Templates", open=False):
        gr.Examples(
            examples=[
                [_TEMPLATE_CLS],
                [_TEMPLATE_DET],
                [_TEMPLATE_SEG],
            ],
            inputs=[yaml_editor],
            label="Click to load a template",
        )

    # -- Event wiring ------------------------------------------------
    yaml_file.change(
        fn=parse_yaml_file,
        inputs=[yaml_file],
        outputs=[yaml_editor],
    )
    yaml_file.change(
        fn=_validate_and_update_btn,
        inputs=[yaml_editor],
        outputs=[output_msg, launch_btn],
    )
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

    queue_selector.change(
        fn=toggle_custom,
        inputs=[queue_selector],
        outputs=[custom_queue],
    )

    launch_btn.click(
        fn=validate_and_launch,
        inputs=[yaml_editor, queue_selector, custom_queue],
        outputs=[output_msg],
    )
    dry_run_btn.click(fn=launch_dry_run, outputs=[output_msg])


# ── Entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    demo.launch(  # noqa: S104
        server_name="0.0.0.0",
        server_port=7860,
        theme=_THEME,
        head=_JS_SHORTCUTS,
        css=_CSS_HIDDEN_DRY_RUN,
    )
