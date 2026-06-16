"""Dynamic Celery configuration for the Worker Invoker.

This module reads configuration from a YAML file and initializes the Celery
application with appropriate broker, backend, and concurrency settings.
"""

import os
from typing import Any

import yaml
from celery import Celery

# 1. READ YAML FIRST (Source of Truth)
CONFIG_PATH: str = "config.yaml"
config: dict[str, Any] = {}
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)

# 2. Extract Redis URL (Priority: Env > YAML > Default)
# Port and DB are considered static for this service
CONTROL_HOST = os.getenv("CONTROL_HOST", "localhost")
REDIS_PORT = 23437
REDIS_DB = 0

REDIS_URL: str = f"redis://{CONTROL_HOST}:{REDIS_PORT}/{REDIS_DB}"

# 3. Initialize Celery App
app: Celery = Celery("ml_cluster", broker=REDIS_URL, backend=REDIS_URL)

# 4. Celery Advanced Configuration
celery_cfg: dict[str, Any] = config.get("celery", {})
worker_settings: dict[str, Any] = {
    "task_routes": {
        "tasks.manage_study": {"queue": "managers"},
        "tasks.train_on_gpu": {"queue": celery_cfg.get("queue", "gpus")},
    },
    # Concurrency control from YAML
    "worker_concurrency": int(celery_cfg.get("concurrency", 1)),
    # Reliability settings for long-running tasks
    "task_acks_late": True,
    "worker_prefetch_multiplier": 1,
    "result_expires": 86400,  # 24 hours
    "worker_send_task_events": True,  # Try enabling to initialize the dispatcher
}

app.conf.update(worker_settings)

print(f"--- [INVOKER:{os.getenv('PRIVATE_QUEUE', 'unknown')}] Celery initialized ---")
print(f"--- [INVOKER:{os.getenv('PRIVATE_QUEUE', 'unknown')}] Celery configuration: {worker_settings} ---")
print(f"--- [INVOKER:{os.getenv('PRIVATE_QUEUE', 'unknown')}] Celery broker: {REDIS_URL} ---")
