# Graph Report - /home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker  (2026-07-30)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 366 nodes · 459 edges · 63 communities (32 shown, 31 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 24 edges (avg confidence: 0.84)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- test_gradio_app.py
- patch
- RunTraining
- dashboard_app.py
- validate_and_launch
- worker_gpu.py
- validate_min_config
- GPU Invoker (Hive Worker) README
- resolve_queue
- launch_dry_run
- Worker Invoker (Celery Worker)
- app.js
- EDA
- LlmAnalizer
- Documentation Index
- manage_worker
- Pre-commit Configuration
- config.py
- app/celery_config.py
- Optuna TPESampler
- load_config
- load_config
- Graphify Rules
- ReadTheDocs Configuration
- add
- CoreService
- graphify.js
- install.sh
- launcher_invoker.sh
- send_task_simple.py
- Headless Test Configuration Root
- coverage.sh
- ML Optimization Multi-Stage Pipeline
- run_tests.sh
- External Service
- uninstall.sh
- Root Requirements
- pause_public_queues.sh
- resume_public_queues.sh
- Worker Invoker Requirements
- task
- Contributor Covenant Code of Conduct
- Docker Images Metadata
- API Boundaries
- Algorithms and Decision Trees
- User Task Relationship
- Invoker Core Validation
- Loguru Integration
- Perimeter Security
- Docker/Proxmox Deployment Guidelines
- Problem Domain Analysis
- invoker_launcher
- Dashboard Service
- Gradio Launcher Service
- Watchtower Service
- GPU Invoker Roadmap
- Worker Dashboard Requirements

## God Nodes (most connected - your core abstractions)
1. `save_template()` - 14 edges
2. `validate_and_launch()` - 14 edges
3. `load_template()` - 12 edges
4. `validate_min_config()` - 12 edges
5. `TestValidateAndLaunch` - 10 edges
6. `resolve_queue()` - 9 edges
7. `TestLoadTemplate` - 9 edges
8. `RunTraining` - 9 edges
9. `TestValidateMinConfig` - 8 edges
10. `TestRunTraining` - 8 edges

## Surprising Connections (you probably didn't know these)
- `Worker Service` --semantically_similar_to--> `Manual Test Sender Container`  [INFERRED] [semantically similar]
  production/docker-compose.yaml → test_manual/docker-compose.yml
- `Root Requirements` --semantically_similar_to--> `Manual Test Dependencies`  [INFERRED] [semantically similar]
  requirements.txt → test_manual/requirements.txt
- `Headless Test Configuration` --semantically_similar_to--> `Headless Test Configuration Root`  [INFERRED] [semantically similar]
  test/test_to_send_invoker.yaml → test_to_send_invoker.yaml
- `Simplified Training and Optuna Parameters` --semantically_similar_to--> `Headless Test Configuration Root`  [INFERRED] [semantically similar]
  test_manual/training_config.yaml → test_to_send_invoker.yaml
- `Worker Invoker Docker Image` --references--> `GPU Invoker (Hive Worker) README`  [INFERRED]
  docker_images.md → README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **YOLO Task Configurations** — ui_gradio_launcher_examples_classification_config_train, ui_gradio_launcher_examples_detection_config_train, ui_gradio_launcher_examples_segmentation_config_train [EXTRACTED 1.00]
- **Invoker Stack Services** — docker_compose_worker, docker_compose_dashboard, docker_compose_gradio_launcher [EXTRACTED 1.00]
- **Manual Invoker-Executor Test Flow** — test_manual_readme_sender, test_manual_readme_workerinv, test_manual_readme_executor [EXTRACTED 1.00]
- **Hive Invoker Core Responsibilities** — index_gpu_allocation, index_samba_client, index_state_machine [EXTRACTED 1.00]

## Communities (63 total, 31 thin omitted)

### Community 0 - "test_gradio_app.py"
Cohesion: 0.08
Nodes (25): File, _handle_upload(), launch_via_executor(), parse_yaml_file(), Parse YAML and store the resulting dict directly in the Redis hash. ``wredis``…, Wrap ``save_template`` with a user-facing status message., Read an uploaded YAML file, validate, persist to Redis, return content. Args:…, Write config to /home/wyolo/request and launch executor container. This… (+17 more)

### Community 1 - "patch"
Cohesion: 0.10
Nodes (22): RedisHashManager, check_redis_connection(), _get_hm(), load_template(), Lazy-init and return the RedisHashManager singleton., Check Redis connectivity and return a human-readable status. Returns: str:…, Load the last saved template from the Redis hash. Supports both formats: a dict…, patch (+14 more)

### Community 2 - "RunTraining"
Cohesion: 0.09
Nodes (20): get_system_limits(), parse_memory_to_bytes(), Any, Run Training State Module. This module defines the RunTraining class, which…, Orchestrates the execution of a training trial in a Docker container. This…, Initializes the RunTraining instance. Args: config (Dict[str, Any]):…, Runs a Docker container with the specified configuration. Args: image_name…, Parses a memory limit string (e.g., '28g', '512m') to bytes. (+12 more)

### Community 3 - "dashboard_app.py"
Cohesion: 0.12
Nodes (27): get, Request, dashboard_home(), get_active_tasks(), get_best_trial(), get_optuna_db(), get_overall_stats(), get_queues() (+19 more)

### Community 4 - "validate_and_launch"
Cohesion: 0.14
Nodes (12): Validate YAML, persist it, and send a Celery task. Args: yaml_content: The YAML…, validate_and_launch(), Tests for the main train-submission function., A fully-valid YAML is accepted and sent., user_id defaults to metadata.author when absent., Existing user_id is preserved., Empty content returns an error., YAML without a model field is rejected. (+4 more)

### Community 5 - "worker_gpu.py"
Cohesion: 0.15
Nodes (17): _merge_configs(), optuna_search(), pause_monitor_thread(), Any, Worker Invoker Module. This module acts as a bridge between Celery and the…, Orchestrates the execution of the training EXECUTOR container. This task…, Simplified task that runs the Executor directly without Optuna. Useful for…, Monitors the pause state in Redis and cancels/adds public queues dynamically. (+9 more)

### Community 6 - "validate_min_config"
Cohesion: 0.17
Nodes (10): Check that the YAML contains all keys needed for a viable training run.…, validate_min_config(), Tests for the minimum-viable-config validator., Returns True for a fully valid config., Returns False for empty content., Detects missing model key., Detects missing metadata.author., Detects missing sweeper.fitness. (+2 more)

### Community 7 - "GPU Invoker (Hive Worker) README"
Cohesion: 0.15
Nodes (15): Worker Configuration (config.yaml), Worker Invoker Component README, Changelog, Docker Compose Orchestration Stack, Simple Dashboard Service, Gradio Launcher Service, Celery Worker Service, Worker Invoker Docker Image (+7 more)

### Community 8 - "resolve_queue"
Cohesion: 0.19
Nodes (9): Resolve the effective queue name from the UI selector. Args: queue_val: The…, resolve_queue(), Tests for the queue-name resolution helper., Private queue value is returned as-is., gpus_high literal is returned as-is., Custom selection returns the typed value., Empty custom box falls back to gpus_high., Whitespace-only custom box falls back to gpus_high. (+1 more)

### Community 9 - "launch_dry_run"
Cohesion: 0.21
Nodes (8): launch_dry_run(), Send a hardcoded dry-run smoke test directly to the invoker. This bypasses the…, Tests for the smoke-test dry-run helper., Dry run sends the correct task and returns a success message., The payload sent includes dry_run: true., Dry run always targets the private queue., A transport error is surfaced., TestLaunchDryRun

### Community 10 - "Worker Invoker (Celery Worker)"
Cohesion: 0.22
Nodes (11): Worker Service, Production Invoker Readme, Celery Connection Configuration, Manual Test Sender Container, Worker Executor (YOLO Training), Manual Test Readme, MLflow Tracking, Optuna DB (+3 more)

### Community 11 - "app.js"
Cohesion: 0.44
Nodes (9): fetchJSON(), loadAll(), loadQueues(), loadStats(), loadStudies(), loadTasks(), loadWorkers(), showStudyDetails() (+1 more)

### Community 12 - "EDA"
Cohesion: 0.29
Nodes (5): EDA, Any, State class for performing Exploratory Data Analysis., Initialize EDA with configuration. Args: config: Worker configuration…, Execute EDA process. Args: training_config: Training configuration. Returns:…

### Community 13 - "LlmAnalizer"
Cohesion: 0.29
Nodes (5): LlmAnalizer, Any, State class for performing post-training analysis with LLMs., Initialize LLM Analyzer with configuration. Args: config: Worker configuration…, Execute LLM analysis process. Args: training_config: Training configuration and…

### Community 14 - "Documentation Index"
Cohesion: 0.25
Nodes (8): FAQ Documentation, Getting Started Documentation, Documentation Index, Tutorials Documentation, GPU Allocation, The Hive Portal, Samba Client, State Machine

### Community 15 - "manage_worker"
Cohesion: 0.47
Nodes (5): get_celery_app(), main(), manage_worker(), Initializes the Celery app with the correct broker., Sends cancel_consumer or add_consumer commands to a specific worker node and…

### Community 16 - "Pre-commit Configuration"
Cohesion: 0.40
Nodes (5): Pre-commit Configuration, MyPy Static Type Checker Check, Pylint Static Analysis Check, Ruff Linter and Formatter Check, Contributing Guidelines

### Community 17 - "config.py"
Cohesion: 0.50
Nodes (3): crear_archivo(), obtener_usuario(), Obtiene el nombre de usuario usando 'whoami'.

### Community 18 - "app/celery_config.py"
Cohesion: 0.50
Nodes (3): print_table(), Dynamic Celery configuration for the Worker Invoker. This module reads…, Prints a formatted table of the Celery configuration and host environment.

### Community 19 - "Optuna TPESampler"
Cohesion: 0.50
Nodes (4): Optuna TPESampler, YOLO Classification config_train.yaml, YOLO Detection config_train.yaml, YOLO Segmentation config_train.yaml

### Community 20 - "load_config"
Cohesion: 0.67
Nodes (3): load_config(), main(), Loads the training configuration.

### Community 21 - "load_config"
Cohesion: 0.67
Nodes (3): launch_task(), load_config(), Loads configuration from file or returns default.

### Community 22 - "Graphify Rules"
Cohesion: 0.67
Nodes (3): Graphify Rules, Graphify Workflow, Gemini System Rules

### Community 23 - "ReadTheDocs Configuration"
Cohesion: 0.67
Nodes (3): ReadTheDocs Configuration, API Reference Documentation RST, Bibliography Documentation RST

### Community 25 - "CoreService"
Cohesion: 0.67
Nodes (3): CoreService, DatabaseAdapter, Domain-Driven Design Principles

### Community 30 - "Headless Test Configuration Root"
Cohesion: 0.67
Nodes (3): Simplified Training and Optuna Parameters, Headless Test Configuration, Headless Test Configuration Root

## Knowledge Gaps
- **59 isolated node(s):** `invoker_launcher`, `state`, `coverage.sh script`, `run_tests.sh script`, `launcher_invoker.sh script` (+54 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **31 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `validate_and_launch()` connect `validate_and_launch` to `test_gradio_app.py`, `resolve_queue`, `validate_min_config`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Why does `validate_min_config()` connect `validate_min_config` to `test_gradio_app.py`, `validate_and_launch`?**
  _High betweenness centrality (0.018) - this node is a cross-community bridge._
- **Why does `resolve_queue()` connect `resolve_queue` to `test_gradio_app.py`, `validate_and_launch`?**
  _High betweenness centrality (0.015) - this node is a cross-community bridge._
- **What connects `invoker_launcher`, `state`, `coverage.sh script` to the rest of the system?**
  _59 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `test_gradio_app.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08067226890756303 - nodes in this community are weakly interconnected._
- **Should `patch` be split into smaller, more focused modules?**
  _Cohesion score 0.0967741935483871 - nodes in this community are weakly interconnected._
- **Should `RunTraining` be split into smaller, more focused modules?**
  _Cohesion score 0.09195402298850575 - nodes in this community are weakly interconnected._