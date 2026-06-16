#!/usr/bin/env python3
# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Script que envía tarea al Invoker y espera resultado.

Este script se ejecuta dentro del contenedor Docker.
"""

import json
import os
import sys
import time

import yaml
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://192.168.1.137:23437/0")
QUEUE_NAME = os.getenv("QUEUE_NAME", "gpus_high")
TASK_NAME = "tasks.train_on_gpu_simple"

app = Celery("test_sender", broker=REDIS_URL, backend=REDIS_URL)


def main():
    print("=" * 60)
    print("DOCKER TEST: Enviando tarea al Invoker")
    print("=" * 60)
    print(f"Redis: {REDIS_URL}")
    print(f"Cola: {QUEUE_NAME}")
    print(f"Tarea: {TASK_NAME}")

    training_config = {
        "train": {
            "model": "yolov8n-cls.pt",
            "data": "/dataset/",
            "epochs": 10,
            "imgsz": 640,
            "batch": 0.85,
            "lr0": 0.01,
            "lrf": 0.01,
            "dropout": 0.0,
            "cos_lr": True,
            "workers": 4,
        },
        "metadata": {
            "author": "docker_test",
            "description": "Prueba desde docker-compose",
        },
        "user_id": "docker_test",
    }

    print("\n[1] Enviando tarea...")
    result = app.send_task(
        TASK_NAME,
        args=[training_config],
        queue=QUEUE_NAME,
    )

    task_id = result.id
    print(f"    Task ID: {task_id}")
    print(f"    Estado: {result.state}")

    print("\n[2] Esperando resultado (timeout: 600s)...")

    try:
        resultado = result.get(timeout=600, propagate=True)

        print("\n" + "=" * 60)
        print("RESULTADO RECIBIDO")
        print("=" * 60)
        print(f"Task ID: {task_id}")
        print(f"Estado: {result.state}")
        print(f"Resultado: {json.dumps(resultado, indent=2)}")

        if resultado.get("accuracy"):
            print(f"\n✓ Accuracy: {resultado['accuracy']}")

        print("=" * 60)
        print("TEST COMPLETADO EXITOSAMENTE")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        print(f"Task ID: {task_id}")
        sys.exit(1)


if __name__ == "__main__":
    main()
