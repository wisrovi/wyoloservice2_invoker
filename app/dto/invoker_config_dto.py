"""Invoker worker configuration schema.

Provides typed validation for local worker settings loaded from YAML or environment.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class InvokerConfigDTO(BaseModel):
    """Pydantic schema representing invoker worker configuration parameters.

    Attributes:
        results_dir (str): Base output directory on host for results.
        redis_url (str): Connection URI for Redis broker.
        storage_url (str): Storage URL for Optuna study database.
        timeout_seconds (int): Default execution watchdog timeout.
        orchestrator (str): Orchestrator type ('docker' or 'k8s').
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    results_dir: str = Field(default="/home/wyolo/train_service_results", description="Results directory")
    redis_url: str = Field(default="redis://192.168.10.252:23437/0", description="Redis broker URL")
    storage_url: str = Field(
        default="postgresql://postgres:postgres@192.168.10.252:23436/wyoloservice",
        description="Optuna PostgreSQL database URL",
    )
    timeout_seconds: int = Field(default=86400, description="Default timeout in seconds")
    orchestrator: str = Field(default="docker", description="Orchestration runtime mode")
