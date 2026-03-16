# Invoker - Celery Worker + Docker Executor

Este componente actúa como **puente entre Celery y Docker**. Escucha tareas de entrenamiento, crea contenedores efímeros para ejecutar el entrenamiento YOLO, y retorna los resultados.

---

## 1. 🚶 Diagram Walkthrough

```mermaid
flowchart TD
    subgraph "Colas Redis"
        Q[Colas: worker_*, gpus_high, gpus_medium, gpus_low]
    end

    subgraph "Invoker Worker"
        C[Celery Worker]
        P1[Pipeline Pre-Train<br/>EDA]
        P2[Pipeline Train<br/>Optuna]
        P3[Pipeline Post-Train<br/>LLM]
        D[Docker SDK]
    end

    subgraph "Docker Engine"
        E[Executor Container]
    end

    subgraph "Volumen Temporal"
        V["/tmp/trial_XXXXX/"]
        V1[config.json]
        V2[results.json]
    end

    Q -->|1. task: train_on_gpu| C
    C -->|2. Run EDA| P1
    C -->|3. Run Training| P2
    P2 -->|4. Crea volumen| V
    P2 -->|5. Escribe config| V1
    P2 -->|6. docker_run| D
    D -->|7. Monta volumen| E
    E -->|8. Lee config| V1
    E -->|9. Entrena YOLO| E
    E -->|10. Escribe results| V2
    E -->>|11. Auto-remove| D
    P2 -->|12. Lee results| V2
    C -->|13. Run Post-Train| P3
    C -->|14. Return accuracy| Q
```

**Flujo Principal:**
1. Invoker recibe tarea `train_on_gpu` de cola
2. Ejecuta pipeline pre-entrenamiento (EDA)
3. Ejecuta pipeline de entrenamiento con Optuna
4. Crea volumen temporal con config.json
5. Ejecuta contenedor Docker con volumen montado
6. Contenedor entrena YOLO y guarda results.json
7. Contenedor se elimina automáticamente
8. Invoker lee accuracy y retorna
9. Ejecuta pipeline post-entrenamiento (LLM)

---

## 2. 🗺️ System Workflow

```mermaid
sequenceDiagram
    participant Q as Redis
    participant C as Invoker Worker
    participant D as Docker Engine
    participant E as Executor Container
    participant V as Volumen
    participant DB as PostgreSQL

    Q->>C: 1. task: train_on_gpu(config)
    
    rect rgb(200, 255, 200)
        note over C: Pipeline Pre-Train
        C->>C: 2. Ejecuta EDA
    end
    
    rect rgb(255, 240, 200)
        note over C: Pipeline Train (Optuna)
        C->>C: 3. Crea /tmp/trial_XXX
        C->>V: 4. Escribe config.json
        
        loop n_trials
            C->>D: 5. docker_run()
            D->>E: 6. Inicia contenedor
            E->>V: 7. Lee config
            E->>DB: 8. Query Optuna trial
            E->>E: 9. Entrena YOLO
            E->>V: 10. Escribe results.json
            E-->>D: 11. Termina (auto-remove)
            C->>V: 12. Lee accuracy
            C->>DB: 13. Guarda resultado
        end
    end
    
    rect rgb(240, 200, 255)
        note over C: Pipeline Post-Train
        C->>C: 14. Ejecuta LLM Analysis
    end
    
    C-->>Q: 15. Retorna accuracy
```

---

## 3. 🏗️ Architecture Components

```mermaid
graph TB
    subgraph "Invoker Worker"
        T[Celery Task<br/>tasks.train_on_gpu]
        P[Pipeline Orchestrator]
        
        subgraph "Pipeline Stages"
            EDA[EDA Stage]
            TRAIN[Train Stage<br/>+ Optuna]
            POST[Post-Train Stage]
        end
        
        D[Docker SDK]
    end

    subgraph "Docker"
        DE[Docker Engine]
        EX[Executor Container]
    end

    subgraph "Persistence"
        R[(Redis<br/>Broker)]
        PG[(PostgreSQL<br/>Optuna DB)]
    end

    T --> P
    P --> EDA
    P --> TRAIN
    P --> POST
    TRAIN --> D
    D --> DE
    DE --> EX
    EX -.-> PG
    R --> T
```

### Componentes Clave

| Componente | Descripción |
|------------|-------------|
| **tasks.train_on_gpu** | Tarea Celery principal |
| **Pipeline Orchestrator** | Orquestador de etapas (EDA → Train → Post) |
| **EDA Stage** | Análisis exploratorio de datos |
| **Train Stage** | Búsqueda Optuna + docker run |
| **Post-Train Stage** | Análisis con LLM |
| **Docker SDK** | bridge.docker para ejecutar contenedores |

---

## 4. ⚙️ Container Lifecycle

### Build Process

1. **Base Image**: Python slim con dependencias Docker SDK
2. **Dependencies**: Instala `celery`, `docker`, `optuna`, `pyyaml`
3. **Code Copy**: Copia worker_gpu.py y states/
4. **Volume Mounts**: Configura /var/run/docker.sock y /tmp
5. **Entrypoint**: Inicia Celery worker

### Runtime Process

1. **Docker Connection**: Conecta a Docker Engine local
2. **Redis Connection**: Conecta al broker
3. **Queue Subscription**: Escucha colas (worker_*, gpus_*)
4. **Volume Creation**: Crea directorios temporales por trial
5. **Container Execution**: Ejecuta contenedores con límites de recursos
6. **Cleanup**: Limpia volúmenes temporales

---

## 5. 📂 File-by-File Guide

| Archivo/Carpeta | Propósito |
|-----------------|-----------|
| `worker_gpu.py` | Tarea Celery `train_on_gpu` |
| `states/run_training.py` | Pipeline de entrenamiento + Docker run |
| `states/eda.py` | Stage de análisis exploratorio |
| `states/llm_analizer.py` | Stage de análisis post-entrenamiento |
| `celery_config.py` | Configuración de Celery |
| `simple_dashboard/` | Dashboard de monitoreo |
| `config.yaml` | Configuración del worker |
| `docker-compose.yml` | Orquestación Docker |

---

## Configuración

```yaml
worker:
  executor_image: "wisrovi/train_service:worker_executor_v1.0.0"
  host_temp_dir: "/tmp"
  cpu_limit_pct: 0.85
  mem_limit_pct: 0.60

celery:
  queue: "gpus"

optuna:
  storage_url: "postgresql://postgres:postgres@192.168.10.252:23436/wyoloservice"
```

---

## Despliegue

```bash
# Worker con cola privada
WORKER_NAME=gpu_node_01 docker-compose up -d

# Comando directo
celery -A worker_gpu worker -Q ${PRIVATE_QUEUE},gpus_high,gpus_medium,gpus_low --concurrency=1
```

---

**William R.** - AI Leader & Solutions Architect
