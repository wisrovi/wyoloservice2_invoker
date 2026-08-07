# Graph Report - wyoloservice2_invoker  (2026-08-05)

## Corpus Check
- 75 files · ~39,684 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 527 nodes · 674 edges · 83 communities (48 shown, 35 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 21 edges (avg confidence: 0.83)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `450c979d`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- TestSaveTemplate
- What You Must Do When Invoked
- RunTraining
- DatasetAnalyzer
- TestValidateAndLaunch
- worker_gpu.py
- validate_min_config
- GPU Invoker (Hive Worker) README
- patch
- TestLaunchDryRun
- Worker Invoker (Celery Worker)
- _get_hm
- test_gradio_app.py
- graphify reference: extra exports and benchmark
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
- graphify reference: query, path, explain
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
- layout.py
- wyoloservice2_invoker — codegraph + graphify
- opencode.json
- graphify reference: add a URL and watch a folder
- graphify reference: commit hook and native CLAUDE.md integration
- graphify reference: incremental update and cluster-only
- graphify reference: GitHub clone and cross-repo merge
- graphify reference: transcribe video and audio
- micro_train.sh
- extraction-spec.md
- telemetry.py
- handlers.py
- TrainingReportAnalyzer
- TestLoadTemplate
- toggle_mode
- TestResultsDownload
- TestCheckRedisConnection
- TestSaveWithFeedback
- TestHandleTrainClick
- load_ui_config
- Simple Dashboard Service

## God Nodes (most connected - your core abstractions)
1. `validate_min_config()` - 15 edges
2. `validate_and_launch()` - 13 edges
3. `_get_hm()` - 12 edges
4. `save_template()` - 12 edges
5. `load_template()` - 12 edges
6. `What You Must Do When Invoked` - 12 edges
7. `check_task_status()` - 11 edges
8. `TestNamedUserTemplates` - 11 edges
9. `TestValidateMinConfig` - 10 edges
10. `TestValidateAndLaunch` - 10 edges

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

## Communities (83 total, 35 thin omitted)

### Community 0 - "TestSaveTemplate"
Cohesion: 0.17
Nodes (7): Tests for the Redis template persistence helper., Returns error message when Redis is unavailable., Returns None on success; stores dict directly., Returns error on invalid YAML., Returns error message on Redis exception., Non-dict YAML (scalar) falls back to empty dict., TestSaveTemplate

### Community 1 - "What You Must Do When Invoked"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 2 - "RunTraining"
Cohesion: 0.08
Nodes (22): get_gpu_usage(), get_system_limits(), parse_memory_to_bytes(), Any, Run Training State Module. This module defines the RunTraining class, which…, Get current GPU utilization percentage from the executor container., Orchestrates the execution of a training trial in a Docker container. This…, Initializes the RunTraining instance. Args: config (Dict[str, Any]):… (+14 more)

### Community 3 - "DatasetAnalyzer"
Cohesion: 0.13
Nodes (19): ClassificationAnalyzer, DatasetAnalyzer, DatasetEDAState, DetectionAnalyzer, Any, Path, Determine whether a YOLO dataset is intended for object detection or…, Analyze a dataset and return its statistics. Parameters ---------- dataset_path… (+11 more)

### Community 4 - "TestValidateAndLaunch"
Cohesion: 0.11
Nodes (10): Tests for the main train-submission function., A fully-valid YAML is accepted and sent., user_id defaults to metadata.author when absent., Existing user_id is preserved., Empty content returns an error., YAML without a model field is rejected., Malformed YAML returns a generic error., Requests always go to the private queue, never a public one. (+2 more)

### Community 5 - "worker_gpu.py"
Cohesion: 0.07
Nodes (30): EDA, Any, State class for performing Exploratory Data Analysis., Initialize EDA with configuration. Args: config: Worker configuration…, Execute EDA process via temporary Executor container. Args: training_config:…, LlmAnalizer, Any, State class for reading the executor-generated LLM training report. (+22 more)

### Community 6 - "validate_min_config"
Cohesion: 0.14
Nodes (12): Basic structural validation of the training config before Celery submission., validate_min_config(), train.epochs must be positive., Scalar YAML is rejected., Tests for the minimum-viable-config validator., Returns True for a fully valid config., Returns False for empty content., Detects missing model key. (+4 more)

### Community 7 - "GPU Invoker (Hive Worker) README"
Cohesion: 0.18
Nodes (12): Worker Configuration (config.yaml), Worker Invoker Component README, Changelog, Docker Compose Orchestration Stack, Gradio Launcher Service, Celery Worker Service, Worker Invoker Docker Image, GPU Invoker (Hive Worker) README (+4 more)

### Community 8 - "patch"
Cohesion: 0.12
Nodes (13): patch, Tests for user-saved, named templates (save/list/load)., Saving without a name returns a warning., Invalid YAML returns an error and does not call Redis., Valid YAML is persisted under the given name., list_user_templates returns sorted names., Returns [] when Redis is offline., load_user_template returns the stored YAML. (+5 more)

### Community 9 - "TestLaunchDryRun"
Cohesion: 0.25
Nodes (5): Tests for the smoke-test dry-run helper., Dry run sends the correct task and returns a success message., The payload sent includes dry_run: true., A transport error is surfaced., TestLaunchDryRun

### Community 10 - "Worker Invoker (Celery Worker)"
Cohesion: 0.22
Nodes (11): Worker Service, Production Invoker Readme, Celery Connection Configuration, Manual Test Sender Container, Worker Executor (YOLO Training), Manual Test Readme, MLflow Tracking, Optuna DB (+3 more)

### Community 11 - "_get_hm"
Cohesion: 0.19
Nodes (15): RedisHashManager, _get_hm(), Lazy-init and return the RedisHashManager singleton., get_template_from_redis(), list_user_templates(), load_template(), load_user_template(), Fetch template from central Redis, or initialize it with default if it doesn't… (+7 more)

### Community 12 - "test_gradio_app.py"
Cohesion: 0.20
Nodes (12): check_redis_connection(), get_local_worker_status(), launch_dry_run(), Validate YAML, persist it locally, and send the corresponding Celery task. The…, Parse YAML and store the resulting dict directly in the Redis hash. ``wredis``…, Send a hardcoded dry-run smoke test directly to the invoker., Check connection to central Redis container., Query Celery active tasks and status of the local worker node. This is an… (+4 more)

### Community 13 - "graphify reference: extra exports and benchmark"
Cohesion: 0.22
Nodes (8): graphify reference: extra exports and benchmark, Step 6b - Wiki (only if --wiki flag), Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 7d - MCP server (only if --mcp flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

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

### Community 43 - "graphify reference: query, path, explain"
Cohesion: 0.33
Nodes (5): For /graphify explain, For /graphify path, graphify reference: query, path, explain, Step 0 — Constrained query expansion (REQUIRED before traversal), Step 1 — Traversal

### Community 62 - "layout.py"
Cohesion: 0.21
Nodes (9): Blocks, get_optuna_engine(), get_optuna_study_history(), list_optuna_studies(), Fetch all study names from PostgreSQL database., Fetch history and best trial details for a specific Optuna study., Initializes and returns SQLAlchemy engine using OPTUNA_DB_URL or default…, build_layout() (+1 more)

### Community 63 - "wyoloservice2_invoker — codegraph + graphify"
Cohesion: 0.40
Nodes (4): Estado, graphify, Sync automático, wyoloservice2_invoker — codegraph + graphify

### Community 64 - "opencode.json"
Cohesion: 0.50
Nodes (3): plugin, $schema, .opencode/plugins/graphify.js

### Community 65 - "graphify reference: add a URL and watch a folder"
Cohesion: 0.50
Nodes (3): For /graphify add, For --watch, graphify reference: add a URL and watch a folder

### Community 66 - "graphify reference: commit hook and native CLAUDE.md integration"
Cohesion: 0.50
Nodes (3): For git commit hook, For native CLAUDE.md integration, graphify reference: commit hook and native CLAUDE.md integration

### Community 67 - "graphify reference: incremental update and cluster-only"
Cohesion: 0.50
Nodes (3): For --cluster-only, For --update (incremental re-extraction), graphify reference: incremental update and cluster-only

### Community 72 - "telemetry.py"
Cohesion: 0.08
Nodes (28): _bar(), check_task_status(), get_executor_stats(), get_host_ip(), get_results_zip(), _idle_llm(), _idle_status(), _llm_status() (+20 more)

### Community 73 - "handlers.py"
Cohesion: 0.20
Nodes (11): File, handle_train_click(), handle_upload(), load_selected_template(), parse_yaml_file(), Load a user-saved template by name into the YAML editor., Read an uploaded YAML file, validate, persist to Redis, return content., Validate config and return (message, button-update). (+3 more)

### Community 74 - "TrainingReportAnalyzer"
Cohesion: 0.29
Nodes (6): Path, Generate a basic report from CSV data when OpenCode fails., Generate AI-assisted training analysis using OpenCode with fallback., Generate a professional training report. Args: results_file: Path to YOLO…, Attempt to generate report using OpenCode with timeout., TrainingReportAnalyzer

### Community 75 - "TestLoadTemplate"
Cohesion: 0.20
Nodes (6): Tests for the Redis template loading helper., Falls back to the bundled classification template when Redis is down., Returns YAML dumped from a stored dict (new format)., Returns YAML from a legacy JSON-string value., Returns raw YAML string (oldest format) as-is., TestLoadTemplate

### Community 76 - "toggle_mode"
Cohesion: 0.24
Nodes (7): Tests for the three-way configuration input selector., example' shows the editor column only., upload' shows the file-upload column only., saved' shows the saved-templates column only., TestToggleMode, Switch visibility between the example, upload and saved-template columns., toggle_mode()

### Community 77 - "TestResultsDownload"
Cohesion: 0.25
Nodes (5): Tests for the ZIP download gating., results_available returns False when nothing has been written., get_results_zip archives the whole results directory., get_results_zip returns None when there are no results., TestResultsDownload

### Community 78 - "TestCheckRedisConnection"
Cohesion: 0.33
Nodes (4): Tests for the Redis connectivity check., Returns green indicator when Redis responds., Returns red indicator when _get_hm returns None., TestCheckRedisConnection

### Community 79 - "TestSaveWithFeedback"
Cohesion: 0.33
Nodes (4): Tests for the user-facing save wrapper., Returns a green status message on success., Passes through the error message from save_template., TestSaveWithFeedback

### Community 80 - "TestHandleTrainClick"
Cohesion: 0.50
Nodes (3): Tests for the train-click handler (auto task-id + tab switch)., An invalid config does not switch tabs., TestHandleTrainClick

## Knowledge Gaps
- **104 isolated node(s):** `$schema`, `.opencode/plugins/graphify.js`, `invoker_launcher`, `coverage.sh script`, `micro_train.sh script` (+99 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **35 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `validate_min_config()` connect `validate_min_config` to `handlers.py`, `test_gradio_app.py`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Why does `validate_and_launch()` connect `test_gradio_app.py` to `_get_hm`, `TestValidateAndLaunch`, `validate_min_config`?**
  _High betweenness centrality (0.014) - this node is a cross-community bridge._
- **Why does `check_task_status()` connect `telemetry.py` to `test_gradio_app.py`?**
  _High betweenness centrality (0.009) - this node is a cross-community bridge._
- **What connects `$schema`, `.opencode/plugins/graphify.js`, `invoker_launcher` to the rest of the system?**
  _104 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `What You Must Do When Invoked` be split into smaller, more focused modules?**
  _Cohesion score 0.08 - nodes in this community are weakly interconnected._
- **Should `RunTraining` be split into smaller, more focused modules?**
  _Cohesion score 0.0846774193548387 - nodes in this community are weakly interconnected._
- **Should `DatasetAnalyzer` be split into smaller, more focused modules?**
  _Cohesion score 0.13227513227513227 - nodes in this community are weakly interconnected._