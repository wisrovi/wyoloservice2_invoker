# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Celery configuration for test_manual scripts.

This module reads from config.yaml and initializes a Celery app
that can send tasks to the Invoker's queue.
"""

import os
from typing import Any

import yaml
from celery import Celery

CONFIG_PATH: str = os.path.join(os.path.dirname(__file__), "config.yaml")

config: dict[str, Any] = {}
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)

redis_cfg: dict[str, Any] = config.get("redis", {})
redis_host: str = os.getenv("CONTROL_HOST", redis_cfg.get("host", "localhost"))
redis_port: int = int(os.getenv("REDIS_PORT", redis_cfg.get("port", 23437)))
redis_db: int = int(os.getenv("REDIS_DB", redis_cfg.get("db", 0)))

REDIS_URL: str = f"redis://{redis_host}:{redis_port}/{redis_db}"

app: Celery = Celery("ml_cluster_test", broker=REDIS_URL, backend=REDIS_URL)

celery_cfg: dict[str, Any] = config.get("celery", {})
TASK_NAME: str = celery_cfg.get("task_name", "tasks.train_on_gpu")
QUEUE_NAME: str = celery_cfg.get("queue", "gpus")

wait_cfg: dict[str, Any] = config.get("wait_result", {})
RESULT_TIMEOUT: int = wait_cfg.get("timeout", 300)
RESULT_INTERVAL: int = wait_cfg.get("interval", 1)

print(f"[TEST] Celery configured for: {REDIS_URL}")
print(f"[TEST] Target queue: {QUEUE_NAME}")
print(f"[TEST] Task name: {TASK_NAME}")
