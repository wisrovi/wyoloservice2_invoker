# Docker Image Naming Convention

All project images follow a standardized naming pattern for consistency across registries and deployments.

## Pattern
`wisrovi/train_service:xxx_vzzz`

- **`xxx`**: The functional block or component (e.g., `control_server`, `manager`, `worker_invoker`, `worker_executor`, `neuralforgeai`).
- **`vzzz`**: The version tag (e.g., `v1.0.0`).

## Image Registry

| Component | Image Name | Description |
| :--- | :--- | :--- |
| **Control Server** | `wisrovi/train_service:control_server_v1.0.0` | FastAPI Gateway + Gradio Interface |
| **Manager** | `wisrovi/train_service/manager:orchestrator_v1.0.0` | Optuna-based orchestrator (Celery worker) |
| **Worker Invoker** | `wisrovi/train_service:worker_invoker_v1.0.0` | Celery worker that manages Docker containers |
| **Worker Executor** | `wisrovi/train_service:worker_executor_v1.0.0` | Ephemeral container for YOLO training |
| **NeuralForgeAI** | `wisrovi/neuralforgeai:v1.0.0` | React frontend UI |
| **Redis** | `redis:7.2` | Message broker (standard image) |
| **PostgreSQL** | `postgres:15` | Optuna study database (standard image) |
| **MLflow** | `ghcr.io/mlflow/mlflow:latest` | Experiment tracking (standard image) |

## Build and Push Commands

```bash
# Control Server (API + Gradio)
docker build -t wisrovi/train_service:control_server_v1.0.0 ./wyoloservice2_control_server
docker push wisrovi/train_service:control_server_v1.0.0

# Manager (Optuna Orchestrator)
docker build -t wisrovi/train_service/manager:orchestrator_v1.0.0 ./wyoloservice2_manager
docker push wisrovi/train_service/manager:orchestrator_v1.0.0

# Worker Invoker
docker build -t wisrovi/train_service:worker_invoker_v1.0.0 ./wyoloservice2_invoker
docker push wisrovi/train_service:worker_invoker_v1.0.0

# Worker Executor (YOLO Training Container)
docker build -t wisrovi/train_service:worker_executor_v1.0.0 ./wyoloservice2_worker/executor
docker push wisrovi/train_service:worker_executor_v1.0.0

# NeuralForgeAI (React Frontend)
docker build -t wisrovi/neuralforgeai:v1.0.0 ./NeuralForgeAI
docker push wisrovi/neuralforgeai:v1.0.0
```

## Docker Compose References

```yaml
# Example docker-compose.yml references
services:
  control_server:
    image: wisrovi/train_service:control_server_v1.0.0
  
  manager:
    image: wisrovi/train_service/manager:orchestrator_v1.0.0
  
  worker:
    image: wisrovi/train_service:worker_invoker_v1.0.0
  
  executor:
    image: wisrovi/train_service:worker_executor_v1.0.0
  
  neuralforgeai:
    image: wisrovi/neuralforgeai:v1.0.0
```

## Environment Variables

```bash
# Required for all services
REDIS_URL=redis://192.168.10.252:23437/0
OPTUNA_DB_URL=postgresql://postgres:postgres@192.168.10.252:23436/wyoloservice

# Worker specific
WORKER_NAME=gpu_node_01
PRIVATE_QUEUE=worker_gpu1
```
