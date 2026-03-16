# Worker Invoker (Orchestrator)

This component acts as a bridge between Celery and the Docker-based Executor. It has been upgraded to manage a complete ML optimization lifecycle using **Optuna** and a modular pipeline system.

## Features

- **Multi-Stage Pipeline:** Support for Pre-training (EDA), Training (Optuna), and Post-training (LLM Analysis).
- **Autonomous Optuna Optimization:** Manages the search for hyperparameters locally, launching multiple trials automatically.
- **Docker-SDK Integration:** Orchestrates ephemeral training containers for each trial, ensuring clean resource management and isolation.
- **Resource Cleanup:** Automatically removes executor containers and temporary trial data after each execution.

## Pipeline Workflow

1.  **EDA Phase:** Initial data analysis before starting the optimization loop.
2.  **Optuna Loop:** 
    -   Suggests hyperparameters based on the configured sampler (TPE, Random, etc.).
    -   Launches a dedicated **Executor** container for training.
    -   Collects metrics and feeds them back to the study.
3.  **LLM Analysis:** Final evaluation of the best trial using language model logic.

## Testing

This project uses `pytest` for unit testing. Follow the instructions below to run tests and calculate coverage.

### Run Tests locally

To run tests in your local environment:

```bash
# From the worker/invoker directory
export PYTHONPATH=\$PYTHONPATH:\$(pwd)
pytest tests/
```

### Run Tests in Docker

To ensure a clean environment, you can run tests using Docker:

```bash
./run_tests.sh
```

## Code Coverage

To calculate code coverage including missing lines:

```bash
./coverage.sh
```

## Project Structure

- `states/`: Contains state-specific logic (e.g., `run_training.py`).
- `tests/`: Unit tests for the component.
- `worker_gpu.py`: Main Celery task definition.
- `requirements.txt`: Python dependencies.
