# GPU Invoker (Hive Worker)

> The Celery-based worker node that manages GPU allocation and Samba dataset mounting.

## Key Features
- **High Performance**: Native parallelism and efficient memory management.
- **Enterprise Security**: Scanned with Bandit, zero exposed credentials.
- **Clean Code**: Pylint score > 9.5 across all Python modules.
- **Resiliency**: Built-in retry mechanisms and state recovery.

## Technical Stack
- Python, Celery, Docker SDK, Samba

## Architecture & Workflow

```mermaid
graph TD;
    A[Client Request] -->|REST/Web| B(GPU Invoker (Hive Worker));
    B -->|Processing| C[(Local Cache/DB)];
    C --> D[Result Output];
```

## Installation & Setup
```bash
git clone <repository_url>
cd wyoloservice2_invoker
# Create virtual environment if applicable
python3 -m venv .venv
source .venv/bin/activate
# Install dependencies
make install || pip install -r requirements.txt
```

## Running Tests
To run the unit tests in a clean and consistent Docker environment:
```bash
bash app/run_tests.sh
```

To calculate code coverage using `pytest-cov` locally:
```bash
cd app
bash coverage.sh
```

## Configuration
Configuration is managed via `control_host.env` and `config.yaml` files. Never commit secrets directly to the codebase.

> [!IMPORTANT]
> For compatibility with **Watchtower** and auto-updates across the 70+ active host deployments, the physical Docker Hub image tag must remain strictly **`wisrovi/train_service:worker_invoker_v1.0.0`**, regardless of the internal logical version (e.g. `v1.3.0`).

## ⚙️ Resource Allocation & Limits (Executor)
To prevent the host machine from freezing or crashing during heavy YOLO trainings, the ephemeral **Executor** container is spawned with strict hardware limits:

*   **CPU Limits (`nano_cpus`)**: Restricts processing power based on `WORKER_CPU_CORES_AVAILABLE` (or `WORKER_CPU_CORES`) defined in `user.env`. Docker restricts CPU cycles at the kernel level, leaving the remaining cores available for the host OS and the Invoker daemon.
*   **RAM Limits (`mem_limit`)**: Enforces memory usage bounds using `WORKER_RAM_MEMORY` from `user.env`.
*   **Shared Memory (`shm_size`)**: Vital for PyTorch dataloaders and multi-process training:
    *   **Minimum Limit**: Strictly bounded to a **minimum of 16 GB** to prevent Out Of Memory (OOM) errors during dataloading.
    *   **Dynamic Scaling**: If `WORKER_RAM_MEMORY` is set to a value higher than 16 GB (e.g., `28g`), SHM scales up to match that RAM allocation. Otherwise, it defaults to `16g` while RAM limits remain at the custom lower value.

## Usage
```bash
# Start the service
make start_all || docker-compose up -d

# Pause public queues (gpus_high, gpus_medium, gpus_low) to listen ONLY to the private queue
make pause-public-queues

# Resume public queues to listen to all queues again
make resume-public-queues

# Remotely pause public queues for a specific worker node with options (temporal or perpetual)
python3 test/manage_remote_worker.py --ip 192.168.1.68 --action pause --mode temporal --hours 4
python3 test/manage_remote_worker.py --ip 192.168.1.68 --action pause --mode perpetual

# Remotely resume public queues for a specific worker node
python3 test/manage_remote_worker.py --ip 192.168.1.68 --action resume

# Stop local development service
make stop

# Stop local service AND clean up any orphan executors or production containers
make stop-all
```

---

## 📜 Changelog & Version History

### Version 1.7.6 (Current Release) - 2026-08-04
*   **One-Click Training Dispatch:** Gradio launcher now validates the YAML and dispatches the Celery training task on the Train button click, auto-switching to the Monitoring tab.
*   **Results ZIP Download:** Added a "Download Results ZIP" button to fetch the training results archive from the worker.
*   **Auto-Refresh Metrics:** Training metric plots now auto-refresh on the status timer tick, in addition to the manual refresh button.
*   **Version Update to v1.7.6:** Bumped version to `v1.7.6`.

### Version 1.7.5 - 2026-08-03
*   **EDA Python command fix:** Resolved syntax error in docker command by changing container command structure to a clean argv list.
*   **Version Update to v1.7.5:** Bumped version to `v1.7.5`.

#### Gradio UI Launcher Updates (v1.1.0) - 2026-08-04
*   **Shared Redis Templates Store:** Moved Classification, Detection, and Segmentation templates to the centralized `invoker:shared_templates` hash in Redis.
*   **Local Saved Template Path:** Local configs saved via "Save Template" are persisted under `invoker:<ip>:template_invoker` to avoid conflicts.
*   **Prominent Destination Queue Banner:** Added a styled, prominent status bar showing the resolved private queue IP at the very top.
*   **Execution Mode Descriptions:** Clearly documented the differences between Simple Training and Full Pipeline modes.
*   **Glassmorphic cockpit design:** Styled the Gradio application with a gorgeous dark theme.

### Version 1.7.4 - 2026-08-03
*   **EDA Temporary Executor Container:** Runs dataset analysis in a short-lived sibling executor container to safely mount network folders and analyze datasets before training.
*   **Version Update to v1.7.4:** Bumped version to `v1.7.4`.

### Version 1.7.3 - 2026-08-03
*   **OpenCode LLM Model Tuning:** Configured `TrainingReportAnalyzer` to use `opencode/deepseek-v4-flash-free` for report generation.
*   **OpenCode Diagnostics Logs:** Prints exit codes and output logs (stdout/stderr) during OpenCode execution.
*   **Version Update to v1.7.3:** Bumped version to `v1.7.3`.

### Version 1.7.2 - 2026-08-03
*   **Dataset Analyzer & OpenCode AI Reports:** Integrated `DatasetAnalyzer` in `EDA` and `TrainingReportAnalyzer` (via OpenCode local LLM execution) in `LlmAnalizer`.
*   **Live Resource Telemetry:** Spawns a background thread in `docker_run` to monitor container CPU, RAM, and GPU stats, exporting them to `telemetry.json` in the results directory.
*   **Gradio Task Checker Panel:** Restructured the Gradio launcher UI to add Live Telemetry readout and a Task Status verification tab (querying Celery AsyncResult).
*   **Version Update to v1.7.2:** Bumped version to `v1.7.2`.

### Version 1.7.1 - 2026-08-03
*   **Fix Default Timeout Inconsistency:** Synchronized default executor timeout to 12 hours (43200 seconds) in `run_training.py` and added configurable option `executor_timeout_seconds` in `config.yaml`. Bumped global version to `v1.7.1`.

### Version 1.5.0 - 2026-07-31
*   **Version Update to v1.5.0:** Bumped core invoker version to reflect recent telemetry, startup registry, and micro-train features.

### Version 1.3.4 (Current Release) - 2026-07-31
*   **Massive Docker Broadcast Pull Command:** Registered a new custom Celery remote control handler (`force_docker_pull`) inside the worker invoker to enable fast, massive cluster-wide image pulling.

### Version 1.3.3 - 2026-07-29
*   **Enforce Minimum SHM Memory Rule:** Implemented specific business logic to set shared memory (`shm_size`) to a minimum of 16 GB. If the user allocates more RAM in `WORKER_RAM_MEMORY` within `user.env` (e.g. `28g`), that larger value is applied for both RAM and SHM; otherwise, SHM defaults to `16g` while RAM respects the custom lower limit.
*   **Rich Telemetry Registration in Redis:** Upgraded task startup blocks to retrieve detailed host environment configurations (`WORKER_HOST`, `WORKER_HOSTNAME`, `WORKER_OS`, `WORKER_CPU_CORES`, `WORKER_GPU_COUNT`, `WORKER_GPU_MODEL`) and store them in Redis under the dedicated `study:<study_id>:invoker_details` key as JSON, as well as embedding these details in the `active_trial` metadata and classic `invoker` string.
*   **Startup Metadata Registration:** Configured worker startup signal handler to serialize host hardware specs, software parameters, and version metadata into a Redis key named `invoker:<ip>:version` on every worker boot.
*   **Micro Train Helper in Container:** Ported 'micro_train.sh' script to run natively inside the invoker container at '/usr/local/bin/micro_train' by installing Docker CLI client within the invoker's Docker image.

### Version 1.3.2 - 2026-07-29
*   **Executor Resource Allocation Fix:** Resolved inconsistencies when mapping CPU and RAM limits to the ephemeral Executor container in [app/states/run_training.py](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/app/states/run_training.py). Unified resource detection to support both `WORKER_CPU_CORES_AVAILABLE` and `WORKER_CPU_CORES` across development and production hosts. Integrated robust memory parsing (supporting units like `28g`) to pass strict byte counts for container limits (`mem_limit` and `shm_size`), aligning logs with Docker runtime restrictions.

### Version 1.3.1 - 2026-07-29
*   **Persistent Pause Options (Temporal & Perpetual):** Upgraded [app/worker_gpu.py](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/app/worker_gpu.py) to monitor dynamic state keys in Redis. Added support for temporal pause (automatically resuming after X hours, default 4 hours configurable via `pause_duration_hours` in [app/config.yaml](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/app/config.yaml)) and perpetual pause (which persists across worker restarts).
*   **Remote Worker Management Upgrade:** Enhanced [test/manage_remote_worker.py](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/test/manage_remote_worker.py) to support `--mode` (`temporal` or `perpetual`) and `--hours` CLI arguments to set persistent pause states in Redis.

### Version 2.0.0 - 2026-07-03
*   **Watchtower API Compatibility Fix:** Configured `DOCKER_API_VERSION=1.44` for the watchtower service in both active host deployment `/home/wisrovi/scripts/docker-compose.yaml` and repository template [production/docker-compose.yaml](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/production/docker-compose.yaml) to resolve the Docker API protocol version mismatch error.
*   **Orphan Container Cleanup Rule:** Added the `stop-all` command in the [Makefile](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/Makefile) to force stop and clean up programmatically created executor containers (`wyolo_executor_*`) and instances running under the systemd production scope.
*   **Celery Node Hostname Fix:** Assigned explicit `hostname: wyolo_invoker_${WORKER_HOST}` in [docker-compose.yaml](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/docker-compose.yaml) to ensure Celery registers the worker with its actual IP address instead of Docker's random short container ID hostname (e.g., `celery@45fa662f178a`).
*   **Remote Worker Management CLI:** Programmed [test/manage_remote_worker.py](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/test/manage_remote_worker.py) to allow administrators and external services (like the Manager) to dynamically add or cancel consumer queues for any worker node in the network by sending targeted Celery control messages via Redis from the outside, without accessing the worker's host or container.
*   **Dynamic Queue Consumer Control:** Added shell scripts and Makefile rules (`pause-public-queues`, `resume-public-queues`) to dynamically pause and resume listening to public queues (gpus_high, gpus_medium, gpus_low) using Celery control broadcast commands isolated to the local node hostname.
*   **Test Environment Alignment:** Updated [test/send_to_invoker_directly.py](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/test/send_to_invoker_directly.py) queue targets and corrected [test_to_send_invoker.yaml](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/test_to_send_invoker.yaml) dataset paths to point to real Samba storage resources, enabling successful end-to-end integration tests.
*   **Config Serialization Fix:** Added recursive data serialization/sanitization in [app/states/run_training.py](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/app/states/run_training.py) to strip non-serializable objects (like `_thread.RLock` and internal metadata injected by wpipe) before writing to YAML/JSON configs for the executor.
*   **Optuna Trial Interface Fix:** Patched [app/worker_gpu.py](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/app/worker_gpu.py) to correct the signature mismatch where Optuna's `Trial` object was incorrectly passed directly to the pipeline. Implemented dynamic parameter sampling from the YAML search space and configuration merging before executing training runs.
*   **Startup Logging Markup Fix:** Corrected rich log syntax errors inside [app/celery_config.py](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/app/celery_config.py) to prevent container crashes caused by unmatched tags during print_table invocations.
*   **Start Configuration Fix:** Patched [production/config.py](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/production/config.py) to look for the control host environment configuration inside the `config/` folder, avoiding GUI locks during execution of headless `make start` routines.
*   **Dynamic CPU allocations:** Upgraded [app/states/run_training.py](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/app/states/run_training.py) to read `WORKER_CPU_CORES_AVAILABLE` dynamically from environment instead of using a hardcoded 8 cores limit, ensuring executor container resource limits are respected.
*   **Rich Log Interface:** Integrated `rich` components (Console, Panel, Table) inside [app/celery_config.py](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/app/celery_config.py) and [app/worker_gpu.py](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/app/worker_gpu.py) to output beautifully formatted startup parameters, trial execution details, and critical host configuration environments (like CPU, RAM, and GPU limits) directly to logs.
*   **Dependency Version Pinning:** Pinned all Python dependencies in [app/requirements.txt](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/app/requirements.txt) to specific production-tested versions (including `optuna==4.8.0`) to avoid potential version mismatches or breaking changes in future deployments.
*   **Dynamic image pulling:** Configured the container runner state to use `pull="always"` for executor runs, guaranteeing active worker nodes always use the latest built Docker Hub layers.
*   **Optuna cancellation routing:** Integrated Celery termination listener to intercept `study.stop()` tasks.
*   **Docker-in-Docker subprocess mounts:** Upgraded Docker API handler to mount Samba CIFS `/wyolo/worker` shares dynamically before launching training trials.

### Version 1.0.0 (Initial Release) - 2026-02-10
*   FastAPI / Celery task listener pulling classification jobs.

---
## Knowledge Graph (Graphify)
This project features a Graphify-powered knowledge graph located in the `graphify-out/` directory.

### Commands & Usage
- **Query the codebase**: Run `graphify query "<your question>"` to trace concepts and code structures.
- **Explain a concept**: Run `graphify explain "<concept>"` to get a detailed summary.
- **Find paths**: Run `graphify path "<A>" "<B>"` to discover relationships between two symbols.
- **Incremental update**: Run `graphify update .` to keep the graph in sync after editing code (AST-only, cost-free).

### Artifacts & Visualizations
- [graph.html](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/graphify-out/graph.html): Interactive graph visualization. Open directly in any browser.
- [GRAPH_REPORT.md](file:///home/william.rodriguez/Documents/w_libraries/train_service2/wyoloservice2_invoker/graphify-out/GRAPH_REPORT.md): Text-based audit report including architectural hubs, communities, and potential knowledge gaps.

---
## Author
**William Steve Rodriguez Villamizar (wisrovi)**
Principal Systems & Software Architect / Technology Evangelist
[LinkedIn Profile](https://es.linkedin.com/in/wisrovi-rodriguez)

