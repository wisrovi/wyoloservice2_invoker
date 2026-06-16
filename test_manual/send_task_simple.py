#!/usr/bin/env python3
# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Script para enviar tareas simplificadas al Invoker via Celery.

Este script envía una tarea directa al Executor sin pasar por Optuna.
Útil para probar el flujo completo Invoker -> Executor -> results.json
"""

import json
import os
import sys
import time

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from celery_config import (
    REDIS_URL,
    RESULT_TIMEOUT,
    app,
)

TASK_NAME = "tasks.train_on_gpu_simple"
QUEUE_NAME = "wisrovi"


def load_config() -> dict:
    config_path = os.path.join(SCRIPT_DIR, "training_config.yaml")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    print("=" * 60)
    print("TEST MANUAL SIMPLE: Envío directo al Executor via Celery")
    print("=" * 60)

    print("\n[1] Configuración de conexión:")
    print(f"    - Redis URL: {REDIS_URL}")
    print(f"    - Cola: {QUEUE_NAME}")
    print(f"    - Tarea: {TASK_NAME}")

    config = load_config()
    train_cfg = config.get("train", {})
    metadata_cfg = config.get("metadata", {})

    print("\n[2] Configuración del entrenamiento:")
    print(f"    - Modelo: {train_cfg.get('model')}")
    print(f"    - Epochs: {train_cfg.get('epochs')}")
    print(f"    - Image size: {train_cfg.get('imgsz')}")

    print("\n[3] Preparando payload...")

    training_config = {
        "train": train_cfg,
        "metadata": metadata_cfg,
        "user_id": metadata_cfg.get("author", "test_user"),
    }

    print(f"    Payload: {json.dumps(training_config, indent=2)[:300]}...")

    print("\n[4] Enviando tarea a Celery...")
    result = app.send_task(
        TASK_NAME,
        args=[training_config],
        queue=QUEUE_NAME,
    )

    task_id = result.id
    print(f"    - Task ID: {task_id}")
    print(f"    - Estado initial: {result.state}")

    print(f"\n[5] Esperando resultado (timeout: {RESULT_TIMEOUT}s)...")

    try:
        result.get(timeout=RESULT_TIMEOUT, propagate=True)

        print("\n[6] Resultado recibido:")
        print(f"    - Estado final: {result.state}")
        print(f"    - Resultado: {result.result}")

        if result.successful():
            print("\n✓ TAREA COMPLETADA EXITOSAMENTE")
        else:
            print(f"\n✗ TAREA FALLIDA: {result.state}")

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        print(f"  Task ID: {task_id}")
        sys.exit(1)

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
