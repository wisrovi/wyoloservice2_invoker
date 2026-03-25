#!/usr/bin/env python3
"""Script para enviar tareas de entrenamiento al Invoker via Celery.

Uso:
    python send_task.py

Requisitos:
    1. Redis corriendo en localhost:6379
    2. Invoker corriendo y escuchando la cola 'gpus'
    3. Executor image disponible: wisrovi/train_service:worker_executor_v1.0.0

El flujo es:
    1. Carga config.yaml para obtener Redis y cola
    2. Carga training_config.yaml para obtener hiperparámetros
    3. Envía tarea a Celery
    4. Espera resultado
    5. Imprime métricas
"""

import os
import sys
import time
import yaml
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from celery_config import (
    app,
    TASK_NAME,
    QUEUE_NAME,
    REDIS_URL,
    RESULT_TIMEOUT,
    RESULT_INTERVAL,
)


def load_config() -> dict:
    """Carga la configuración de entrenamiento."""
    config_path = os.path.join(SCRIPT_DIR, "training_config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    print("=" * 60)
    print("TEST MANUAL: Envío de tarea al Invoker via Celery")
    print("=" * 60)

    print(f"\n[1] Configuración de conexión:")
    print(f"    - Redis URL: {REDIS_URL}")
    print(f"    - Cola: {QUEUE_NAME}")
    print(f"    - Tarea: {TASK_NAME}")

    config = load_config()
    train_cfg = config.get("train", {})
    study_cfg = config.get("study", {})
    metadata_cfg = config.get("metadata", {})

    print(f"\n[2] Configuración del entrenamiento:")
    print(f"    - Modelo: {train_cfg.get('model')}")
    print(f"    - Epochs: {train_cfg.get('epochs')}")
    print(f"    - Image size: {train_cfg.get('imgsz')}")
    print(f"    - Learning rate: {train_cfg.get('lr0')}")

    print(f"\n[3] Preparando payload para Celery...")

    training_config = {
        "train": train_cfg,
        "sweeper": {
            "study_name": study_cfg.get("name", "test_study"),
            "direction": study_cfg.get("direction", "maximize"),
            "n_trials": study_cfg.get("n_trials", 1),
            "sampler": study_cfg.get("sampler", "TPESampler"),
        },
        "metadata": metadata_cfg,
        "user_id": metadata_cfg.get("author", "test_user"),
    }

    print(f"    Payload JSON (primeros 500 chars):")
    payload_json = json.dumps(training_config, indent=2)
    print(f"    {payload_json[:500]}...")

    print(f"\n[4] Enviando tarea a Celery...")
    result = app.send_task(
        TASK_NAME,
        args=[training_config],
        queue=QUEUE_NAME,
    )

    task_id = result.id
    print(f"    - Task ID: {task_id}")
    print(f"    - Estado inicial: {result.state}")

    print(f"\n[5] Esperando resultado (timeout: {RESULT_TIMEOUT}s)...")

    try:
        result.get(timeout=RESULT_TIMEOUT, propagate=True)

        print(f"\n[6] Resultado recibido:")
        print(f"    - Estado final: {result.state}")
        print(f"    - Resultado: {result.result}")

        if result.successful():
            print("\n✓ TAREA COMPLETADA EXITOSAMENTE")
            if isinstance(result.result, dict):
                if "accuracy" in result.result:
                    print(f"  Accuracy: {result.result['accuracy']}")
                if "best_params" in result.result:
                    print(f"  Best params: {result.result['best_params']}")
        else:
            print(f"\n✗ TAREA FALLIDA: {result.state}")

    except Exception as e:
        print(f"\n✗ ERROR esperando resultado: {e}")
        print(f"  Task ID: {task_id}")
        print(f"  Revisa los logs del Invoker para más detalles")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("TEST MANUAL COMPLETADO")
    print("=" * 60)


if __name__ == "__main__":
    main()
