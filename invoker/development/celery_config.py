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
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

# 2. Extract Redis URL (Priority: YAML > Env > Default)
redis_cfg: dict[str, Any] = config.get("redis", {})
redis_host: str = redis_cfg.get("host", "localhost")

# validate if port is in host, if not, set default port
if ":" in redis_host:
    redis_host = redis_host.split(":")[0]
    redis_port = redis_host.split(":")[1]
else:
    redis_port: int = int(redis_cfg.get("port", 6379))

redis_db: int = int(redis_cfg.get("db", 0))

# Build URL from YAML components
DEFAULT_REDIS_URL: str = f"redis://{redis_host}:{redis_port}/{redis_db}"
# Only use env if YAML doesn't have it or if explicitly set
REDIS_URL: str = str(redis_cfg.get("url", os.getenv("REDIS_URL", DEFAULT_REDIS_URL)))

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
