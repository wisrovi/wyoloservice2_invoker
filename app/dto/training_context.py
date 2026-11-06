"""Training context schema for WPipe invoker pipeline.

Defines the typed Pydantic context passed between state machine steps.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class TrainingContext(BaseModel):
    """Execution context containing configuration and telemetry for training jobs.

    Attributes:
        training_config (Dict[str, Any]): Full training and sweeper configuration.
        task_id (Optional[str]): Celery task identifier.
        study_id (Optional[str]): Optuna study identifier.
        eda_results (Dict[str, Any]): Exploratory data analysis metrics.
        training_results (Dict[str, Any]): Execution output and validation scores.
        llm_analysis (Dict[str, Any]): LLM generated summary and diagnostics.
        status (str): Current workflow status string.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    training_config: Dict[str, Any] = Field(default_factory=dict, description="Job configuration")
    task_id: Optional[str] = Field(default=None, description="Celery task ID")
    study_id: Optional[str] = Field(default=None, description="Optuna study ID")
    eda_results: Dict[str, Any] = Field(default_factory=dict, description="EDA analysis payload")
    training_results: Dict[str, Any] = Field(default_factory=dict, description="Executor results")
    llm_analysis: Dict[str, Any] = Field(default_factory=dict, description="LLM report payload")
    status: str = Field(default="initialized", description="Current step status")
