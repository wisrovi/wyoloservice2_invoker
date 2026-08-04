import re

import gradio as gr
import yaml

import celery_client
from celery_client import _HASH_KEY, save_template, validate_min_config
from templates import list_user_templates, load_template, load_user_template, save_user_template

_TASK_ID_RE = re.compile(r"Task ID:.*?`([^`]+)`")

def _save_with_feedback(content: str) -> str:
    """Wrap save_template with a user-facing status message."""
    err = save_template(content)
    if err:
        return err
    return f"🟢 Template saved → `{_HASH_KEY}`"

def save_named_template_with_feedback(name: str, content: str) -> tuple[str, dict]:
    """Save the YAML under a user-chosen name and refresh the saved-templates list.

    Returns (message, dropdown-update).
    """
    err = save_user_template(name, content)
    if err:
        return err, gr.update(choices=list_user_templates())
    return (
        f"🟢 Template **{name}** guardado → `{list_user_templates()}`",
        gr.update(choices=list_user_templates(), value=name),
    )

def load_selected_template(name: str) -> str:
    """Load a user-saved template by name into the YAML editor."""
    return load_user_template(name)

def toggle_task_id_edit(is_editing: bool) -> tuple[dict, dict, bool]:
    """Toggle the Task ID box between read-only and editable.

    The Task ID is auto-filled when Train is clicked, so it is read-only by
    default. Clicking the pencil enables manual editing (e.g. to inspect a
    different run), and clicking again locks it back.
    """
    if is_editing:
        return (
            gr.update(interactive=False),
            gr.update(value="✏️ Editar", variant="secondary"),
            False,
        )
    return (
        gr.update(interactive=True),
        gr.update(value="🔒 Bloquear", variant="primary"),
        True,
    )

def parse_yaml_file(file: gr.File | None) -> str:
    """Read an uploaded YAML file, validate, persist to Redis, return content."""
    if file is None:
        return load_template()
    try:
        with open(file.name, encoding="utf-8") as f:
            content = f.read()
        yaml.safe_load(content)
        save_template(content)
        return content
    except Exception as exc:
        return f"Error reading YAML: {exc}"

def _validate_and_update_btn(yaml_content: str) -> tuple[str, dict]:
    """Validate config and return (message, button-update)."""
    valid, msg = validate_min_config(yaml_content)
    return msg, gr.update(interactive=valid)

def toggle_mode(mode: str) -> tuple[dict, dict]:
    """Switch visibility between editor and file upload columns."""
    if mode == "upload":
        return gr.update(visible=False), gr.update(visible=True)
    return gr.update(visible=True), gr.update(visible=False)

def handle_upload(file: gr.File | None) -> tuple[str, str, dict]:
    """Process uploaded config files and return (validated_content, validation_msg, btn_state)."""
    if file is None:
        return "", "", gr.update(interactive=False)
    content = parse_yaml_file(file)
    if content.startswith("Error"):
        return "", f"❌ {content}", gr.update(interactive=False)
    valid, msg = validate_min_config(content)
    return content, msg, gr.update(interactive=valid)

def handle_train_click(yaml_content: str) -> tuple[str, str, dict]:
    """
    Validates config and dispatches Celery training task.
    The execution mode (full pipeline vs direct) and destination queue are
    controlled by config.yaml, never by UI widgets.
    Returns:
        - output_msg (Markdown string)
        - task_id (string to populate task_id_box)
        - tabs (Gradio gr.update to switch selected tab to monitoring)
    """
    result_msg = celery_client.validate_and_launch(yaml_content)

    # Extract task ID from output message (robust to message wording)
    task_id = ""
    match = _TASK_ID_RE.search(result_msg)
    if match:
        task_id = match.group(1)

    if task_id:
        # Switch to monitoring tab — task id is auto-filled in the box
        return result_msg, task_id, gr.update(selected="monitoring_tab")
    return result_msg, "", gr.update()
