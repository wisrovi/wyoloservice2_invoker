"""Docstring."""

REDIS_HOST = "192.168.10.252"


import os

import yaml
from celery import Celery

# --- User Configuration (Hardcoded) ---
# Modify these variables according to your needs
REDIS_HOST = os.getenv("CONTROL_HOST", REDIS_HOST)
REDIS_PORT = "23437"
QUEUE_NAME = "192.168.1.68"  # Options: gpus_high, gpus_medium, gpus_low, default

# Path to your YAML configuration file
YAML_CONFIG_PATH = "test_to_send_invoker.yaml"

# Internal YAML Template (used if YAML_CONFIG_PATH is not found)
DEFAULT_CONFIG = {
    "debug": "192.168.1.68",
    "model": "yolov8n.pt",
    "type": "yolo",
    "train": {
        "batch": -1,
        "data": "/examples/ArchitecturePlan/data.yaml",
        "epochs": 2,
        "imgsz": 640,
    },
    "sweeper": {
        "study_name": "exp_detection_headless",
        "fitness": "metrics/mAP50-95(B)",
    },
    "metadata": {
        "author": "William Rodriguez - wisrovi",
        "content": "Experiment launched from headless script",
    },
}

# --- Infrastructure Setup ---
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
celery_app = Celery("neuralforge_launcher", broker=REDIS_URL, backend=REDIS_URL)


def load_config():
    """Loads configuration from file or returns default."""
    if os.path.exists(YAML_CONFIG_PATH):
        print(f"[*] Loading configuration from {YAML_CONFIG_PATH}...")
        with open(YAML_CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f)
    else:
        print(f"[!] {YAML_CONFIG_PATH} not found. Using hardcoded default configuration.")

        # save the default_config
        with open(YAML_CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(DEFAULT_CONFIG, f)

        return DEFAULT_CONFIG


def launch_task():
    payload = load_config()

    # Basic Validation
    if not payload.get("model") or not payload.get("type"):
        print("[-] Error: 'model' and 'type' are required fields in the configuration.")
        return

    # Set user_id if missing
    if "user_id" not in payload:
        payload["user_id"] = payload.get("metadata", {}).get("author", "wisrovi")

    try:
        task_name = "tasks.train_on_gpu_simple"
        result = celery_app.send_task(task_name, args=[payload], queue=QUEUE_NAME)

        print("\n" + "=" * 40)
        print("✅ Training Task Sent Successfully!")
        print(f"ID:    {result.id}")
        print(f"Queue: {QUEUE_NAME}")
        print(f"Model: {payload['model']}")
        print(f"Type:  {payload['type']}")
        print("=" * 40)

    except Exception as e:
        print(f"[-] Critical Error sending task: {e}")


if __name__ == "__main__":
    launch_task()
