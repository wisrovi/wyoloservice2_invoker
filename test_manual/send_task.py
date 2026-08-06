#!/usr/bin/env python3
# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Script to send training tasks to the Invoker via Celery.

Usage:
    python send_task.py

Requirements:
    1. Redis running at localhost:6379
    2. Invoker running and listening to the 'gpus' queue
    3. Executor image available: wisrovi/train_service:worker_executor_v1.0.0

The flow is:
    1. Load config.yaml to get Redis and queue
    2. Load training_config.yaml to get hyperparameters
    3. Send task to Celery
    4. Wait for result
    5. Print metrics
"""

import json
import os
import sys
import time

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from celery_config import (
    QUEUE_NAME,
    REDIS_URL,
    RESULT_INTERVAL,
    RESULT_TIMEOUT,
    TASK_NAME,
    app,
)


def load_config() -> dict:
    """Loads the training configuration."""
    config_path = os.path.join(SCRIPT_DIR, "training_config.yaml")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    print("=" * 60)
    print("MANUAL TEST: Sending task to Invoker via Celery")
    print("=" * 60)

    print("\n[1] Connection configuration:")
    print(f"    - Redis URL: {REDIS_URL}")
    print(f"    - Queue: {QUEUE_NAME}")
    print(f"    - Task: {TASK_NAME}")

    config = load_config()
    train_cfg = config.get("train", {})
    study_cfg = config.get("study", {})
    metadata_cfg = config.get("metadata", {})

    print("\n[2] Training configuration:")
    print(f"    - Model: {train_cfg.get('model')}")
    print(f"    - Epochs: {train_cfg.get('epochs')}")
    print(f"    - Image size: {train_cfg.get('imgsz')}")
    print(f"    - Learning rate: {train_cfg.get('lr0')}")

    print("\n[3] Preparing payload for Celery...")

    training_config = {
        "model": train_cfg.get("model"),
        "type": "yolo",
        "train": train_cfg,
        "sweeper": {
            "study_name": study_cfg.get("name", "test_study"),
            "direction": study_cfg.get("direction", "maximize"),
            "n_trials": study_cfg.get("n_trials", 1),
            "sampler": study_cfg.get("sampler", "TPESampler"),
            "fitness": study_cfg.get("fitness", "metrics/accuracy_top1"),
        },
        "metadata": metadata_cfg,
        "user_id": metadata_cfg.get("author", "test_user"),
    }

    print("    Payload JSON (first 500 chars):")
    payload_json = json.dumps(training_config, indent=2)
    print(f"    {payload_json[:500]}...")

    print("\n[4] Sending task to Celery...")
    result = app.send_task(
        TASK_NAME,
        args=[training_config],
        queue=QUEUE_NAME,
    )

    task_id = result.id
    print(f"    - Task ID: {task_id}")
    print(f"    - Initial status: {result.state}")

    print(f"\n[5] Waiting for result (timeout: {RESULT_TIMEOUT}s)...")

    try:
        result.get(timeout=RESULT_TIMEOUT, propagate=True)

        print("\n[6] Result received:")
        print(f"    - Final status: {result.state}")
        print(f"    - Result: {result.result}")

        if result.successful():
            print("\n✓ TASK COMPLETED SUCCESSFULLY")
            if isinstance(result.result, dict):
                if "accuracy" in result.result:
                    print(f"  Accuracy: {result.result['accuracy']}")
                if "best_params" in result.result:
                    print(f"  Best params: {result.result['best_params']}")
        else:
            print(f"\n✗ TASK FAILED: {result.state}")

    except Exception as e:
        print(f"\n✗ ERROR waiting for result: {e}")
        print(f"  Task ID: {task_id}")
        print("  Check the Invoker logs for more details")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("MANUAL TEST COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()
