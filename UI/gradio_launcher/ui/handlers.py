import yaml
import gradio as gr
import celery_client
from celery_client import save_template, validate_min_config, _HASH_KEY
from templates import load_template

def _save_with_feedback(content: str) -> str:
    """Wrap save_template with a user-facing status message."""
    err = save_template(content)
    if err:
        return err
    return f"🟢 Template saved → `{_HASH_KEY}`"

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
    Returns:
        - output_msg (Markdown string)
        - task_id (string to populate task_id_box)
        - tabs (Gradio gr.update to switch selected tab to monitoring)
    """
    result_msg = celery_client.validate_and_launch(yaml_content)
    
    # Extract task ID from output message
    task_id = ""
    if "🆔 **Task ID:**" in result_msg:
        try:
            parts = result_msg.split("🆔 **Task ID:** `")
            if len(parts) > 1:
                task_id = parts[1].split("`")[0]
        except Exception:
            pass
            
    if task_id:
        # Switch to monitoring tab
        return result_msg, task_id, gr.update(selected="monitoring_tab")
    return result_msg, "", gr.update()
