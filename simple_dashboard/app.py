"""Dashboard API for Optuna Studies and Celery Workers.

This module provides a REST API to monitor and manage Optuna hyperparameter
optimization studies and Celery worker status.
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from celery import Celery
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

CONFIG: dict[str, Any] = {}
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "invoker", "config.yaml"
)
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        CONFIG = yaml.safe_load(f)

# 1. Database Connection (PostgreSQL)
optuna_cfg: dict[str, Any] = CONFIG.get("optuna", {})
OPTUNA_DB_URL = os.getenv(
    "OPTUNA_DB_URL",
    optuna_cfg.get("storage_url", "postgresql://optuna_user:optuna_pass@localhost/optuna_db")
)

engine = create_engine(OPTUNA_DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

redis_cfg: dict[str, Any] = CONFIG.get("redis", {})
redis_host: str = redis_cfg.get("host", "localhost")
redis_port: int = int(redis_cfg.get("port", 6379))
redis_db: int = int(redis_cfg.get("db", 0))
REDIS_URL: str = f"redis://{redis_host}:{redis_port}/{redis_db}"

celery_app: Celery = Celery("dashboard", broker=REDIS_URL, backend=REDIS_URL)

app = FastAPI(
    title="ML Training Dashboard",
    description="Monitor and manage Optuna studies and Celery workers",
    version="1.0.0",
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def get_optuna_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """Render the main dashboard page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/api/studies")
async def list_studies() -> dict[str, Any]:
    """List all Optuna studies."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    study_id,
                    study_name,
                    direction,
                    best_value,
                    best_params,
                    n_trials,
                    datetime(start_time / 1000, 'unixepoch') as start_time,
                    datetime(_end_time_ / 1000, 'unixepoch') as end_time
                FROM studies
                ORDER BY start_time DESC
            """))
            rows = result.fetchall()

        studies = []
        for row in rows:
            study = dict(row._mapping)
            if study.get("best_params"):
                study["best_params"] = json.loads(study["best_params"])
            studies.append(study)

        return {"studies": studies, "count": len(studies)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/studies/{study_name}")
async def get_study(study_name: str) -> dict[str, Any]:
    """Get detailed information about a specific study."""
    try:
        conn = get_optuna_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT 
                study_id,
                study_name,
                direction,
                best_value,
                best_params,
                n_trials,
                datetime(start_time / 1000, 'unixepoch') as start_time,
                datetime(_end_time_ / 1000, 'unixepoch') as end_time
            FROM studies
            WHERE study_name = ?
        """,
            (study_name,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(
                status_code=404, detail=f"Study '{study_name}' not found"
            )

        study = dict(row)
        if study.get("best_params"):
            study["best_params"] = json.loads(study["best_params"])

        return study
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/studies/{study_name}/trials")
async def get_study_trials(study_name: str) -> dict[str, Any]:
    """Get all trials for a specific study."""
    try:
        conn = get_optuna_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT 
                t.trial_id,
                t.study_id,
                t.state,
                t.value,
                t.datetime_start as start_time,
                t.datetime_complete as end_time,
                t.params,
                t.user_attrs
            FROM trials t
            JOIN studies s ON t.study_id = s.study_id
            WHERE s.study_name = ?
            ORDER BY t.trial_id
        """,
            (study_name,),
        )
        rows = cursor.fetchall()
        conn.close()

        trials = []
        for row in rows:
            trial = dict(row)
            if trial.get("params"):
                trial["params"] = json.loads(trial["params"])
            if trial.get("user_attrs"):
                trial["user_attrs"] = json.loads(trial["user_attrs"])
            trials.append(trial)

        return {"trials": trials, "count": len(trials)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/studies/{study_name}/best")
async def get_best_trial(study_name: str) -> dict[str, Any]:
    """Get the best trial for a specific study."""
    try:
        conn = get_optuna_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT 
                t.trial_id,
                t.study_id,
                t.state,
                t.value,
                t.datetime_start as start_time,
                t.datetime_complete as end_time,
                t.params,
                t.user_attrs
            FROM trials t
            JOIN studies s ON t.study_id = s.study_id
            WHERE s.study_name = ? AND t.state = 'COMPLETE'
            ORDER BY t.value DESC
            LIMIT 1
        """,
            (study_name,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"No completed trials found for study '{study_name}'",
            )

        trial = dict(row)
        if trial.get("params"):
            trial["params"] = json.loads(trial["params"])
        if trial.get("user_attrs"):
            trial["user_attrs"] = json.loads(trial["user_attrs"])

        return trial
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/studies/{study_name}/trials/running")
async def get_running_trials(study_name: str) -> dict[str, Any]:
    """Get currently running trials for a study."""
    try:
        conn = get_optuna_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT 
                t.trial_id,
                t.study_id,
                t.state,
                t.datetime_start as start_time,
                t.params
            FROM trials t
            JOIN studies s ON t.study_id = s.study_id
            WHERE s.study_name = ? AND t.state = 'RUNNING'
            ORDER BY t.trial_id
        """,
            (study_name,),
        )
        rows = cursor.fetchall()
        conn.close()

        trials = []
        for row in rows:
            trial = dict(row)
            if trial.get("params"):
                trial["params"] = json.loads(trial["params"])
            trials.append(trial)

        return {"running_trials": trials, "count": len(trials)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workers")
async def get_workers() -> dict[str, Any]:
    """Get Celery worker status."""
    try:
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        active = inspect.active()
        reserved = inspect.reserved()

        workers = []
        if stats:
            for worker_name, worker_stats in stats.items():
                workers.append(
                    {
                        "name": worker_name,
                        "status": "online",
                        "stats": worker_stats,
                        "active_tasks": active.get(worker_name, []) if active else [],
                        "reserved_tasks": reserved.get(worker_name, [])
                        if reserved
                        else [],
                    }
                )

        return {"workers": workers, "count": len(workers)}
    except Exception as e:
        return {"workers": [], "count": 0, "error": str(e)}


@app.get("/api/workers/active-tasks")
async def get_active_tasks() -> dict[str, Any]:
    """Get all active Celery tasks."""
    try:
        inspect = celery_app.control.inspect()
        active = inspect.active()

        tasks = []
        if active:
            for worker_name, worker_tasks in active.items():
                for task in worker_tasks:
                    tasks.append(
                        {
                            "worker": worker_name,
                            "id": task.get("id"),
                            "name": task.get("name"),
                            "args": task.get("args", []),
                            "kwargs": task.get("kwargs", {}),
                        }
                    )

        return {"tasks": tasks, "count": len(tasks)}
    except Exception as e:
        return {"tasks": [], "count": 0, "error": str(e)}


@app.get("/api/queues")
async def get_queues() -> dict[str, Any]:
    """Get Celery queue information."""
    try:
        inspect = celery_app.control.inspect()
        active_queues = inspect.active_queues()

        queues = []
        if active_queues:
            for worker_name, worker_queues in active_queues.items():
                for queue in worker_queues:
                    queues.append(
                        {
                            "worker": worker_name,
                            "name": queue.get("name"),
                            "items": queue.get("items", 0),
                        }
                    )

        return {"queues": queues, "count": len(queues)}
    except Exception as e:
        return {"queues": [], "count": 0, "error": str(e)}


@app.get("/api/stats")
async def get_overall_stats() -> dict[str, Any]:
    """Get overall statistics for studies and workers."""
    try:
        conn = get_optuna_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM studies")
        total_studies = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) as count FROM trials")
        total_trials = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) as count FROM trials WHERE state = 'COMPLETE'")
        completed_trials = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) as count FROM trials WHERE state = 'RUNNING'")
        running_trials = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) as count FROM trials WHERE state = 'FAIL'")
        failed_trials = cursor.fetchone()["count"]

        conn.close()

        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        worker_count = len(stats) if stats else 0

        return {
            "studies": {
                "total": total_studies,
            },
            "trials": {
                "total": total_trials,
                "completed": completed_trials,
                "running": running_trials,
                "failed": failed_trials,
            },
            "workers": {
                "online": worker_count,
            },
        }
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
