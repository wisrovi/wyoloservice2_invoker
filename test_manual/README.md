# Test Manual - Invoker

Pruebas manuales del flujo Invoker-Executor via Celery y Docker.

## Estructura

```
test_manual/
├── config.yaml              # Configuración de conexión Redis
├── training_config.yaml     # Hiperparámetros del entrenamiento
├── celery_config.py        # Módulo de conexión Celery (para scripts)
├── send_task.py           # Envía tarea directamente (desarrollo)
├── send_task_docker.py    # Envía tarea (para docker)
├── Dockerfile             # Imagen del contenedor de prueba
├── docker-compose.yml     # Orquestación Docker
├── requirements.txt       # Dependencias Python
└── README.md             # Este archivo
```

## Arquitectura del Sistema

```mermaid
flowchart TB
    subgraph INFRASTRUCTURE["🖥️ Infraestructura"]
        Redis[(Redis<br/>192.168.1.137:23437)]
        Optuna[(PostgreSQL<br/>Optuna DB)]
        MLflow[(MLflow<br/>Tracking)]
    end
    
    subgraph CONTAINERS["🐳 Contenedores Docker"]
        Sender[test_sender<br/>send_task_docker.py]
        WorkerInv[worker_invoker<br/>Celery Worker]
        Executor[worker_executor<br/>YOLO Training]
    end
    
    Sender -->|"send_task()"| Redis
    Redis -->|"Celery Queue"| WorkerInv
    WorkerInv -->|"docker.run()"| Executor
    Executor -->|"results.json"| WorkerInv
    WorkerInv -->|"result.get()"| Sender
    
    WorkerInv -->|"Optuna Study"| Optuna
    WorkerInv -->|"Metrics"| MLflow
    
    style Sender fill:#90EE90,stroke:#228B22
    style WorkerInv fill:#87CEEB,stroke:#4169E1
    style Executor fill:#FFB6C1,stroke:#DC143C
```

## Flujo de Datos Completo

```mermaid
sequenceDiagram
    participant Sender as test_sender
    participant Redis as Redis Queue
    participant Worker as Worker Invoker
    participant Executor as Executor Container
    participant Host as Docker Host
    
    Note over Sender: Usuario ejecuta<br/>docker-compose up
    
    Sender->>Redis: send_task(tasks.train_on_gpu_simple)
    Note right of Sender: Payload JSON:<br/>{train: {...}, metadata: {...}}
    
    Redis->>Worker: Task en cola gpus_high
    Worker->>Worker: Recibe task de Celery
    
    Worker->>Host: Crea temp_dir en /tmp
    Worker->>Host: Escribe config.json
    Note over Host: /tmp/trial_xxx/config.json
    
    Worker->>Executor: docker.run(executor_image)
    Note over Executor: Lee config.json<br/>Ejecuta entrenamiento<br/>Simula 5 minutos
    
    Executor->>Host: Escribe results.json
    Note over Host: /tmp/trial_xxx/results.json<br/>{accuracy: 0.869}
    
    Executor--x Executor: Container termina
    Note over Executor: remove=True en docker.run()
    
    Worker->>Host: Lee results.json
    Worker->>Redis: Task SUCCESS con accuracy
    
    Sender->>Sender: result.get() retorna
    Note over Sender: Imprime resultado<br/>Contenedor termina
```

## Uso Rápido

```bash
# 1. Asegúrate que Redis y Worker estén corriendo
docker ps | grep redis
ps aux | grep celery | grep worker

# 2. Ejecutar prueba
cd test_manual
docker-compose up --build

# 3. El contenedor:
#    - Envía tarea a Celery
#    - Espera resultado del Executor
#    - Imprime resultados
#    - Muere

# 4. Repetir
docker-compose up --build
```

## Flujo Visual Paso a Paso

```mermaid
flowchart LR
    subgraph ENVIO["📤 Envío"]
        A1[docker-compose up] --> A2[Build imagen]
        A2 --> A3[Ejecuta send_task_docker.py]
        A3 --> A4[Celery send_task()]
    end
    
    subgraph PROCESO["⚙️ Procesamiento"]
        A4 --> B1[Redis cola gpus_high]
        B1 --> B2[Worker Invoker recibe]
        B2 --> B3[Ejecutor Docker]
        B3 --> B4[Entrenamiento ~5min]
        B4 --> B5[results.json]
    end
    
    subgraph RESPUESTA["📥 Respuesta"]
        B5 --> C1[Worker lee accuracy]
        C1 --> C2[Celery result.get()]
        C2 --> C3[Imprime resultado]
        C3 --> C4[✓ TEST COMPLETADO]
    end
    
    style ENVIO fill:#90EE90
    style PROCESO fill:#87CEEB
    style RESPUESTA fill:#FFD700
```

## Salida Esperada

```
============================================================
DOCKER TEST: Enviando tarea al Invoker
============================================================
Redis: redis://192.168.1.137:23437/0
Cola: gpus_high
Tarea: tasks.train_on_gpu_simple

[1] Enviando tarea...
    Task ID: abc123-def456-...
    Estado: PENDING

[2] Esperando resultado (timeout: 600s)...

============================================================
RESULTADO RECIBIDO
============================================================
Task ID: abc123-def456-...
Estado: SUCCESS
Resultado: {
  "status": "done",
  "accuracy": 0.869,
  "invoker": "test_worker"
}

✓ Accuracy: 0.869
============================================================
TEST COMPLETADO EXITOSAMENTE
============================================================
```

## Requisitos Previos

1. **Redis** corriendo en `192.168.1.137:23437`
2. **Worker Invoker** escuchando la cola `gpus_high`

### Iniciar Worker Invoker (si no está corriendo)

```bash
cd ../invoker/development
REDIS_URL=redis://192.168.1.137:23437/0 \
PRIVATE_QUEUE=test_worker \
celery -A worker_gpu worker \
-Q gpus_high \
--loglevel=info \
--concurrency=1 \
--hostname=test_worker@%h
```

### Ver Workers Activos

```bash
docker exec environment-redis-1 redis-cli KEYS "*"
ps aux | grep celery | grep worker
```

## Configuración

### config.yaml (para scripts de desarrollo)

```yaml
redis:
  host: "192.168.1.137"
  port: 23437
  db: 0

celery:
  queue: "gpus_high"
  task_name: "tasks.train_on_gpu_simple"
```

### docker-compose.yml

```yaml
services:
  test_sender:
    build: .
    environment:
      - REDIS_URL=redis://192.168.1.137:23437/0
      - QUEUE_NAME=gpus_high
    network_mode: host
```

### training_config.yaml

```yaml
train:
  model: "yolov8n-cls.pt"
  epochs: 10
  imgsz: 640
  lr0: 0.01
  batch: 0.85
```

## Estructura de Datos

```mermaid
classDiagram
    class TrainingConfig {
        +dict train
        +dict metadata
        +str user_id
    }
    
    class TrainParams {
        +str model
        +str data
        +int epochs
        +int imgsz
        +float batch
        +float lr0
        +float lrf
        +float dropout
        +bool cos_lr
        +int workers
    }
    
    class Metadata {
        +str author
        +str description
    }
    
    class Result {
        +str status
        +float accuracy
        +str invoker
    }
    
    TrainingConfig *-- TrainParams : train
    TrainingConfig *-- Metadata : metadata
    Result ..> TrainParams : contiene
```

## Troubleshooting

### Error: Connection refused

```bash
# Verificar Redis
docker exec environment-redis-1 redis-cli ping
# Debe responder: PONG
```

### Cola vacía, worker no recibe

```bash
# Ver colas
docker exec environment-redis-1 redis-cli KEYS "*"

# Limpiar y reintentar
docker exec environment-redis-1 redis-cli FLUSHALL
docker-compose up --build
```

### Worker no levanta executor

```bash
# Ver logs del worker
cat /tmp/worker_test.log

# Ver contenedores executor
docker ps | grep executor
```

## Desarrollo (sin Docker)

Para probar directamente sin docker-compose:

```bash
pip install -r requirements.txt
python send_task.py
```

O usar el worker local:

```bash
cd ../invoker/development
celery -A worker_gpu worker -Q gpus_high --loglevel=info
```
