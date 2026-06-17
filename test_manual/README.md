# Manual Test - Invoker

Manual tests of the Invoker-Executor flow via Celery and Docker.

## Structure

```
test_manual/
├── config.yaml              # Redis connection configuration
├── training_config.yaml     # Training hyperparameters
├── celery_config.py        # Celery connection module (for scripts)
├── send_task.py           # Sends task directly (development)
├── send_task_docker.py    # Sends task (for docker)
├── Dockerfile             # Test container image
├── docker-compose.yml     # Docker orchestration
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## System Architecture

```mermaid
flowchart TB
    subgraph INFRASTRUCTURE["🖥️ Infrastructure"]
        Redis[(Redis<br/>192.168.1.137:23437)]
        Optuna[(PostgreSQL<br/>Optuna DB)]
        MLflow[(MLflow<br/>Tracking)]
    end

    subgraph CONTAINERS["🐳 Docker Containers"]
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

## Complete Data Flow

```mermaid
sequenceDiagram
    participant Sender as test_sender
    participant Redis as Redis Queue
    participant Worker as Worker Invoker
    participant Executor as Executor Container
    participant Host as Docker Host

    Note over Sender: User executes<br/>docker-compose up

    Sender->>Redis: send_task(tasks.train_on_gpu_simple)
    Note right of Sender: JSON Payload:<br/>{train: {...}, metadata: {...}}

    Redis->>Worker: Task in gpus_high queue
    Worker->>Worker: Receives Celery task

    Worker->>Host: Creates temp_dir in /tmp
    Worker->>Host: Writes config.json
    Note over Host: /tmp/trial_xxx/config.json

    Worker->>Executor: docker.run(executor_image)
    Note over Executor: Reads config.json<br/>Executes training<br/>Simulates 5 minutes

    Executor->>Host: Writes results.json
    Note over Host: /tmp/trial_xxx/results.json<br/>{accuracy: 0.869}

    Executor--x Executor: Container finishes
    Note over Executor: remove=True in docker.run()

    Worker->>Host: Reads results.json
    Worker->>Redis: Task SUCCESS with accuracy

    Sender->>Sender: result.get() returns
    Note over Sender: Prints result<br/>Container finishes
```

## Quick Start

```bash
# 1. Make sure Redis and Worker are running
docker ps | grep redis
ps aux | grep celery | grep worker

# 2. Run test
cd test_manual
docker-compose up --build

# 3. The container:
#    - Sends task to Celery
#    - Waits for Executor result
#    - Prints results
#    - Dies

# 4. Repeat
docker-compose up --build
```

## Visual Step-by-Step Flow

```mermaid
flowchart LR
    subgraph SEND["📤 Send"]
        A1[docker-compose up] --> A2[Build image]
        A2 --> A3[Execute send_task_docker.py]
        A3 --> A4[Celery send_task()]
    end

    subgraph PROCESS["⚙️ Processing"]
        A4 --> B1[Redis gpus_high queue]
        B1 --> B2[Worker Invoker receives]
        B2 --> B3[Docker Executor]
        B3 --> B4[Training ~5min]
        B4 --> B5[results.json]
    end

    subgraph RESPONSE["📥 Response"]
        B5 --> C1[Worker reads accuracy]
        C1 --> C2[Celery result.get()]
        C2 --> C3[Print result]
        C3 --> C4[✓ TEST COMPLETED]
    end

    style SEND fill:#90EE90
    style PROCESS fill:#87CEEB
    style RESPONSE fill:#FFD700
```

## Expected Output

```
============================================================
DOCKER TEST: Sending task to Invoker
============================================================
Redis: redis://192.168.1.137:23437/0
Queue: gpus_high
Task: tasks.train_on_gpu_simple

[1] Sending task...
    Task ID: abc123-def456-...
    Status: PENDING

[2] Waiting for result (timeout: 600s)...

============================================================
RESULT RECEIVED
============================================================
Task ID: abc123-def456-...
Status: SUCCESS
Result: {
  "status": "done",
  "accuracy": 0.869,
  "invoker": "test_worker"
}

✓ Accuracy: 0.869
============================================================
TEST COMPLETED SUCCESSFULLY
============================================================
```

## Previous Requirements

1. **Redis** running at `192.168.1.137:23437`
2. **Worker Invoker** listening to the `gpus_high` queue

### Start Worker Invoker (if not running)

```bash
cd ../app
REDIS_URL=redis://192.168.1.137:23437/0 \
PRIVATE_QUEUE=test_worker \
celery -A worker_gpu worker \
-Q gpus_high \
--loglevel=info \
--concurrency=1 \
--hostname=test_worker@%h
```

### View Active Workers

```bash
docker exec environment-redis-1 redis-cli KEYS "*"
ps aux | grep celery | grep worker
```

## Configuration

### config.yaml (for development scripts)

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

## Data Structure

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
    Result ..> TrainParams : contains
```

## Troubleshooting

### Error: Connection refused

```bash
# Verify Redis
docker exec environment-redis-1 redis-cli ping
# Should respond: PONG
```

### Empty queue, worker does not receive

```bash
# View queues
docker exec environment-redis-1 redis-cli KEYS "*"

# Clear and retry
docker exec environment-redis-1 redis-cli FLUSHALL
docker-compose up --build
```

### Worker does not start executor

```bash
# View worker logs
cat /tmp/worker_test.log

# View executor containers
docker ps | grep executor
```

## Development (without Docker)

To test directly without docker-compose:

```bash
pip install -r requirements.txt
python send_task.py
```

Or use the local worker:

```bash
cd ../app
celery -A worker_gpu worker -Q gpus_high --loglevel=info
```
