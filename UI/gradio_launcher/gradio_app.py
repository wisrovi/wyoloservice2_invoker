# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Gradio Launcher for NeuralForge AI.

This module provides a web interface to launch training tasks on the GPU cluster.
"""

import json
import os

import gradio as gr
import yaml
from celery import Celery

# --- Configuration ---
REDIS_HOST = os.getenv("CONTROL_HOST", "localhost")
REDIS_PORT = "23437"
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

# Initialize Celery
celery_app = Celery("gradio_launcher", broker=REDIS_URL, backend=REDIS_URL)

# YAML templates (Internal)
EXAMPLE_CLS = """model: "yolov8n-cls.pt"
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

EXAMPLE_DET = """model: "yolov8n.pt"
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

EXAMPLE_SEG = """model: "yolov8n-seg.pt"
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

# Examples for gr.Examples: [Path/Name, Queue, Hidden_YAML_Content]
# We use a trick: the third element is the actual content, but we will handle the mapping
EXAMPLES = [
    ["/app/examples/classification/config_train.yaml", "gpus_high", EXAMPLE_CLS],
    ["/app/examples/detection/config_train.yaml", "gpus_medium", EXAMPLE_DET],
    ["/app/examples/segmentation/config_train.yaml", "gpus_low", EXAMPLE_SEG],
]


def parse_yaml_file(file):
    """Parse a YAML file and return its content as a string."""
    if file is None:
        return ""
    try:
        with open(file.name, encoding="utf-8") as f:
            content = f.read()
            yaml.safe_load(content)
            return content
    except Exception as e:
        return f"Error reading YAML: {str(e)}"


def validate_and_launch(yaml_content, queue):
    """Validate YAML content and launch a Celery task."""
    if not yaml_content.strip():
        return "❌ Error: YAML configuration is empty."

    if yaml_content.startswith("Error"):
        return f"❌ {yaml_content}"

    try:
        payload = yaml.safe_load(yaml_content)

        # Validation of required root fields
        if "model" not in payload:
            return "❌ Error: The YAML must contain the 'model' field at the root."
        if "type" not in payload:
            return "❌ Error: The YAML must contain the 'type' field at the root (e.g., 'yolo')."

        # Defaults if missing
        if "user_id" not in payload:
            payload["user_id"] = payload.get("metadata", {}).get("author", "unknown_user")

        task_name = "tasks.train_on_gpu_simple"
        result = celery_app.send_task(task_name, args=[payload], queue=queue)

        status_msg = (
            f"✅ Training sent!\n\nID: {result.id}\nQueue: {queue}\n\n"
            f"Structure detected:\n- Model: {payload['model']}\n- Type: {payload['type']}"
        )
        return status_msg

    except Exception as e:
        return f"❌ Syntax or sending error: {str(e)}"


# --- UI Theme ---
theme = gr.themes.Soft(
    primary_hue="blue",
    secondary_hue="slate",
    neutral_hue="gray",
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
)

with gr.Blocks(theme=theme, title="NeuralForge Launcher") as demo:
    gr.Markdown("# 🚀 NeuralForge AI: Cluster Training")
    gr.Markdown("Select a template or upload your YAML to launch the training.")

    with gr.Row():
        with gr.Column(scale=2):
            gr.Markdown("### 📄 YAML Configuration")
            yaml_file = gr.File(label="Upload .yaml file", file_types=[".yaml", ".yml"])
            yaml_editor = gr.Code(label="YAML Editor", language="yaml", lines=18, interactive=False)

        with gr.Column(scale=1):
            gr.Markdown("### ⚙️ Send Parameters")
            queue_form = gr.Dropdown(
                choices=["gpus_high", "gpus_medium", "gpus_low", "default"],
                label="Priority Queue",
                value="gpus_high",
                info="Select the processing queue.",
            )

            # Hidden field to help gr.Examples trigger logic if needed,
            # but here we just map directly to yaml_editor
            dummy_hidden = gr.Textbox(visible=False)

            launch_btn = gr.Button("🔥 Train", variant="primary", size="lg")
            output_msg = gr.Textbox(label="System Status", lines=8, interactive=False)

    # Examples Section
    gr.Markdown("### 💡 Available Templates")
    gr.Examples(
        examples=EXAMPLES,
        inputs=[dummy_hidden, queue_form, yaml_editor],
        label="Select a path to load its content",
    )

    # Event Handlers
    yaml_file.change(fn=parse_yaml_file, inputs=[yaml_file], outputs=[yaml_editor])

    launch_btn.click(fn=validate_and_launch, inputs=[yaml_editor, queue_form], outputs=[output_msg])

if __name__ == "__main__":
    # B104: Binding to all interfaces is intended for Docker containers
    demo.launch(server_name="0.0.0.0", server_port=7860)  # nosec
