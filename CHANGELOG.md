# Changelog - GPU Invoker (Hive)

## [2.3.4] - 2026-10-29
### Added
- **Default Natural Resource Bounds (30% GPU, 6GB RAM, 2 CPU cores, 8GB SHM):**
  - Configured baseline natural limits in `run_training.py` (`MAX_GPU=30`, `WORKER_RAM_MEMORY=6g`, `WORKER_CPU_CORES_AVAILABLE=2.0`, `WORKER_SHM_MEMORY=8g`) ensuring that newly started or unconfigured invokers never consume beyond these boundaries, safeguarding developer desktop responsiveness during active work.

## [2.3.3] - 2026-10-28
### Fixed
- **Host Desktop Freeze & Resource Starvation Prevention:**
  - Enforced idle process priority (`nice -n 19 ionice -c 3`) on the training executor command, guaranteeing that the Linux kernel CFS scheduler immediately yields CPU cycles to interactive developer applications (X11, Wayland, IDEs, browser).
  - Enforced defensive OpenMP, MKL, OpenBLAS, and PyTorch CPU thread caps (`OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `TORCH_NUM_THREADS <= 4`) to prevent CPU thread explosion and 100% host CPU lockups.
  - Dynamically reserved at least 35-40% of host RAM (minimum 4-6GB) strictly for the host operating system and developer desktop apps, capping executor RAM to at most 60% of total physical RAM to eliminate swap thrashing.
  - Replaced hardcoded 16GB minimum `/dev/shm` tmpfs allocation with bounded size (`max(2Gi, min(8Gi, 35% RAM))`), preventing unswappable kernel memory exhaustion on <= 24GB workstations.
  - Removed `priorityClassName: system-node-critical` from Kubernetes executor Pod manifests to prevent preemption and starvation of interactive host and system processes.

### Version Update
- Bumped Invoker version to `v2.3.3` and `RunTraining` state version to `1.1.2`.

## [2.2.0] - 2026-10-22
### Added
- **Node-Level Drain & Eviction Monitoring:**
  - Added checks in `DockerOrchestrator` and `KubernetesOrchestrator` (`check_docker_cancellation` and `check_k8s_cancellation`) for `invoker:{worker_ip}:cancel_active` and `invoker:{worker_ip}:drain` (with `evict: true`).
  - When an invoker node is marked for draining with eviction by the cluster controller, active executor containers and pods are immediately terminated (`container.kill()`), terminating the training trial in seconds and freeing up GPUs.
  - Added support for `:cancelled` key alongside `:cancel`.
- **Drain Mode Celery Queue Suppression:**
  - Updated `setup_pause_monitor` in `worker_gpu.py` to recognize `"draining"` state and automatically suppress public Celery queue consumers (`gpus_high`, `gpus_medium`, `gpus_low`, `wyolo_gpu_queue`).

### Version Update
- Synchronized Invoker version to `v2.2.0` matching the global `train_service2` ecosystem.

## [2.1.0] - 2026-10-21
### Added
- **Real-Time Task Cancellation & Abort:**
  - Integrated live cancellation listeners in `DockerOrchestrator` and `KubernetesOrchestrator` checking `wyolo:task:{task_id}:cancel`, `study:{study_id}:cancel`, and `task:{task_id}:cancel` in Redis.
  - Aborts running Docker executor containers (`container.kill()`) and cleans up Kubernetes Pods immediately, freeing GPU memory in seconds.
  - Generates `status: "cancelled"` in `results.json` upon operator-triggered abort.
- **Dynamic & Multi-GPU Assignment:**
  - Added `get_optimal_gpu_device` helper that automatically selects the GPU with highest free VRAM via `nvidia-smi` when not explicitly specified, eliminating OOM collisions.
  - Added support for explicit GPU indexing (`gpu_id: "1"`), multi-GPU device list (`device_ids: ["0", "1"]`), and `gpu_id: "all"` for distributed data-parallel (DDP) training.
- **Real Hardware & GPU Telemetry:**
  - Added real GPU utilization reporting via `nvidia-smi` into Redis stats and `telemetry.json` across both Docker and Kubernetes orchestration modes.
  - Integrated Kubernetes Metrics Server API queries (`/apis/metrics.k8s.io/v1beta1/...`) to extract real pod CPU and memory usage in K8s environments.
- **Pre-Flight GPU Health Checks:**
  - Implemented `check_gpu_health()` utilizing `nvidia-smi` to test driver responsiveness and detect hardware PCIe bus / Xid errors before launching training tasks.
  - Integrated automated public queue pause when GPU errors are detected to avoid burning valid queue tasks.
- **Node Heartbeat TTL & Storage Guard:**
  - Added lightweight Redis heartbeat (`invoker:{worker_host}:heartbeat`) with 30-second TTL updated every 10 seconds for real-time node liveness detection.
  - Added continuous disk space guard on `/home/wyolo` and results volumes, pausing public consumers if disk capacity drops below critical thresholds (< 5%).
- **Startup Orphan Container Sweeper:**
  - Added automated cleanup sweeping stale or orphaned `wyolo_executor_*` and `wyolo_eda_runner_*` containers and Pods when the invoker worker boots up.
- **Queue Alignment & Legacy Drain:**
  - Added `wyolo_gpu_queue` to default Celery queue consumers in Docker Compose and dynamic pause monitor to ensure stranded legacy tasks are drained.

### Version Update
- Synchronized Invoker version to `v2.1.0` matching the global `train_service2` ecosystem.

## [1.9.5] - 2026-10-06
### Added
- **Hybrid Orchestration Architecture (`orchestrator.py`):**
  - Dual orchestration engine supporting both standalone Docker environments and native Kubernetes clusters.
  - Automatically detects cluster execution via `ORCHESTRATOR` or in-cluster ServiceAccount token.
  - When in Kubernetes mode, spawns ephemeral Pods pinned to the local node (`nodeName: WORKER_HOSTNAME`) via native REST API, streaming logs in real time.
  - Fully integrated with Dozzle web UI (`http://localhost:8888`), allowing browser-based one-click deletion/stopping of training tasks without terminal access.
  - Refactored `EDA` and `RunTraining` states to use `get_orchestrator()`.

### Version Update
- Bumped invoker version to `v1.9.5`.

## [1.9.4] - 2026-08-25
### Fixed
- **LLM analyzer model:** replaced dead `opencode/deepseek-v4-flash-free` with `opencode/nemotron-3.5-lightning-free` in `training_report_analyzer.py`. Model is now configurable via `LLM_MODEL` env var.

### Version Update
- Bumped invoker version to `v1.9.4`.

## [1.9.3] - 2026-08-25
### Fixed
- **Optuna study naming:** `optuna_search` now resolves the study name from `sweeper.study_name` (falling back to top-level `study_name`, then the dated default). Previously the user-provided name was ignored because it was read from the wrong nesting level, so every run created a new `study_YYYYMMDD_<hash>` study and Optuna lost its cross-run warm-start history.

## [1.9.2] - 2026-08-24
### Fixed
- **Optuna storage DB:** `optuna_search` now connects to the dedicated `optuna_db` instead of the shared `wyoloservice` PostgreSQL database. MLflow's Alembic migrations on the shared DB overwrite the generic `alembic_version` table, causing every `create_study` to fail with "The runtime optuna version 4.8.0 is no longer compatible with the table schema". Aligns the invoker with the manager's existing convention.
- **Gradio launcher DB:** default study-listing URL in `UI/gradio_launcher/db.py` moved to `optuna_db`.
- **EDA path translation:** `/datasets/...` paths are now translated to `/wyolo/control_server/datasets/...` before running `DatasetAnalyzer` inside the temporary executor container (which has no root `/datasets`), fixing `FileNotFoundError` during EDA.

### Version Update
- Bumped invoker version to `v1.9.2`.

## [1.7.5] - 2026-08-03
### Fixed
- Corrected python command list structure inside the docker container call in `EDA` to avoid syntax errors with single quotes.

### Gradio UI Launcher Changes:
#### [v1.1.0] - 2026-08-04
- **Redis Templates Refactor:** Moved shared templates to `invoker:shared_templates` hash in central Redis, and local saved config template to `invoker:<ip>:template_invoker`.
- **Destination Queue Prominence:** Added a prominent, highly styled target queue banner at the top of the UI to display the resolved private worker queue (derived from host's IP/hostname).
- **Execution Mode Clarifications:** Added markdown text explaining the exact functional difference between Simple Training (direct) and Full Pipeline execution modes.
- **Glassmorphic Cockpit Style:** Styled the UI with a beautiful, high-contrast dark theme.
- **Standalone UI deployment:** Added `Dockerfile`, `docker-compose.yaml`, and `Makefile` under the `UI/` folder.

## [1.7.4] - 2026-08-03
### Added
- Implemented Option A (Temporary Container execution) for the `EDA` state dataset analysis.

## [1.7.3] - 2026-08-03
### Changed
- Configured `TrainingReportAnalyzer` to explicitly use `opencode/deepseek-v4-flash-free` LLM model.
- Added diagnostics stdout/stderr logging outputs for OpenCode execution.

## [1.7.2] - 2026-08-03
### Added
- Integrated Dataset Imbalance and Type Detector (`DatasetAnalyzer`) in `EDA` state.
- Integrated OpenCode AI report generation (`TrainingReportAnalyzer`) in `LlmAnalizer` state.
- Added background thread resource utilization telemetry monitoring (CPU, RAM, GPU, current epoch).
- Restructured Gradio UI to include Live Telemetry metrics and Task Status check panel.

## [1.7.1] - 2026-08-03
### Fixed
- Fixed default executor container timeout inconsistency, changing the container wait timeout from 1 hour to 12 hours (43200 seconds) and adding the `executor_timeout_seconds` configuration option in config.yaml.

## [1.1.0] - 2026-05-27
### Added
- Robust Samba (CIFS) mounting logic with auto-retry.
- Improved Docker resource cleaning after trial failure.
- New marketing landing page.
