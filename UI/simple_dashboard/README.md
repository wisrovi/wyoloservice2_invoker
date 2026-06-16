# Worker Dashboard

This component provides a REST API and a web interface to monitor and manage Optuna hyperparameter optimization studies and Celery worker status.

## Features

- **Optuna Integration:** Read and display results from Optuna studies.
- **Worker Monitoring:** Real-time status of Celery workers using `celery_app.control.inspect()`.
- **API Endpoints:** REST endpoints for studies, trials, workers, and queues.

## Architecture

The dashboard connects directly to the same Redis instance as the workers and reads study data from the shared Optuna database.

## Usage

### Run locally

```bash
# From the worker/dashboard directory
pip install -r requirements.txt
python app.py
```

### Run with Docker

The dashboard is part of the `docker-compose.yml` stack (optional).

```bash
docker-compose up -d dashboard
```

## API Documentation

The dashboard is built with FastAPI, and interactive documentation is available at `/docs` or `/redoc`.
