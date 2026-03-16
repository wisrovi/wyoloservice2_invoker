# wyoloservice2_invoker - Worker Invoker (Orquestador)

Este componente actúa como un puente entre Celery y el Docker-based Executor. Ha sido mejorado para gestionar un ciclo de vida completo de optimización ML usando **Optuna** y un sistema de pipeline modular.

## Arquitectura del Flujo

```mermaid
graph TD
    subgraph "Celery Task: tasks.train_on_gpu"
        C[Celery Broker<br/>Redis]
        W[Invoker Worker<br/>Celery]
        
        subgraph "Pipeline de 3 Fases"
            P1[1. Pre-Training<br/>EDA Analysis]
            P2[2. Training<br/>Optuna Search]
            P3[3. Post-Training<br/>LLM Analysis]
        end
        
        D[Docker Engine]
        E[Executor Container]
        DB[(PostgreSQL<br/>Optuna DB)]
    end
    
    C -->|Celery Task| W
    W -->|Run| P1
    W -->|Run| P2
    W -->|Run| P3
    
    P2 -->|docker_run| D
    D -->|Run| E
    E -->|Query Params| DB
    E -->|results.json| W
```

## Características

- **Pipeline Multi-Etapa:** Soporte para Pre-entrenamiento (EDA), Entrenamiento (Optuna), y Post-entrenamiento (Análisis LLM).
- **Optimización Autónoma con Optuna:** Gestiona la búsqueda de hiperparámetros localmente, lanzando múltiples trials automáticamente.
- **Integración Docker-SDK:** Orquestra contenedores de entrenamiento efímeros para cada trial, asegurando gestión limpia de recursos y aislamiento.
- **Limpieza de Recursos:** Elimina automáticamente contenedores executor y datos temporales de cada ejecución después de completarse.

## Flujo del Pipeline

```mermaid
sequenceDiagram
    participant C as Celery Broker
    participant W as Invoker Worker
    participant D as Docker Engine
    participant DB as PostgreSQL
    
    C->>W: task: train_on_gpu(config)
    
    rect rgb(200, 255, 200)
        note over W: FASE 1: EDA
        W->>W: Ejecuta Análisis Exploratorio
    end
    
    rect rgb(255, 240, 200)
        note over W: FASE 2: OPTUNA
        loop n_trials times
            W->>DB: Consulta próximo trial
            DB-->>W: Parámetros sugeridos
            W->>D: docker run executor
            D-->>W: results.json
            W->>DB: Guarda resultado
        end
    end
    
    rect rgb(240, 200, 255)
        note over W: FASE 3: LLM
        W->>W: Análisis final del mejor trial
    end
    
    W-->>C: Retorna mejor accuracy
```

## Configuración

### config.yaml

```yaml
# Worker Config - Total Control
redis:
  host: "192.168.1.137"  # IP del Servidor Central
  port: 6379
  db: 0

optuna:
  # IP y Puerto del servidor central (Postgres distribuido)
  storage_url: "postgresql://postgres:postgres@192.168.10.252:23436/wyoloservice"

celery:
  concurrency: 1        # Cuántos contenedores executor lanzar a la vez
  loglevel: "INFO"
  queue: "gpus"

worker:
  executor_image: "wisrovi/train_service:worker_executor_v1.0.0"
  host_temp_dir: "/tmp"  # Carpeta en el HOST para volúmenes efímeros
  cpu_limit_pct: 0.85    # % máximo de cores a usar
  mem_limit_pct: 0.60    # % máximo de RAM a usar
```

## Despliegue con Docker Compose

```bash
# Con cola privada específica
WORKER_NAME=gpu_node_01 docker-compose up -d

# Ver logs
docker logs worker_gpu_node_01
```

## Estructura del Proyecto

```
wyoloservice2_invoker/
├── invoker/
│   ├── development/          # Código principal
│   │   ├── worker_gpu.py     # Definición de tareas Celery
│   │   ├── states/           # Lógica por fase
│   │   │   ├── run_training.py
│   │   │   ├── eda.py
│   │   │   └── llm_analizer.py
│   │   ├── celery_config.py
│   │   └── config.yaml
│   └── production/           # Scripts de despliegue
├── simple_dashboard/          # Dashboard de monitoreo
├── docker-compose.yml         # Orquestación
└── README.md
```

## Testing

### Ejecutar tests localmente

```bash
# Desde el directorio worker/invoker
export PYTHONPATH=$PYTHONPATH:$(pwd)
pytest tests/
```

### Ejecutar tests en Docker

```bash
./run_tests.sh
```

### Cobertura de código

```bash
./coverage.sh
```

---

**William R.** - AI Leader & Solutions Architect
