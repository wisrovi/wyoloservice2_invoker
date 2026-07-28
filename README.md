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

## Configuration
Configuration is managed via `control_host.env` and `config.yaml` files. Never commit secrets directly to the codebase.

## Usage
```bash
# Start the service
make start_all || docker-compose up -d
```

---

## 📜 Changelog & Version History

### Version 2.0.0 (Current Release) - 2026-07-03
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
## Author
**William Steve Rodriguez Villamizar (wisrovi)**
Principal Systems & Software Architect / Technology Evangelist
[LinkedIn Profile](https://es.linkedin.com/in/wisrovi-rodriguez)
