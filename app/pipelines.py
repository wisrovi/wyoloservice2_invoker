"""Declarative WPipe pipeline assembly for Worker Invoker.

Assembles state machine pipelines for pre-training EDA, containerized training execution,
and post-training LLM analysis.
"""

from typing import Any, Dict
from states.eda import EDA
from states.llm_analizer import LlmAnalizer
from states.run_training import RunTraining
from wpipe.pipe import Pipeline


def create_pretrain_pipeline(config: Dict[str, Any]) -> Pipeline:
    """Construct pipeline for Exploratory Data Analysis prior to model training.

    Args:
        config (Dict[str, Any]): Worker invoker configuration dictionary.

    Returns:
        Pipeline: Configured WPipe pipeline instance for EDA.
    """
    invoker_eda_pipeline = Pipeline()
    invoker_eda_pipeline.set_steps([(EDA(config), EDA.NAME, EDA.VERSION)])
    return invoker_eda_pipeline


def create_training_pipeline(config: Dict[str, Any]) -> Pipeline:
    """Construct pipeline for Docker/K8s container execution and trial evaluation.

    Args:
        config (Dict[str, Any]): Worker invoker configuration dictionary.

    Returns:
        Pipeline: Configured WPipe pipeline instance for model training.
    """
    invoker_train_pipeline = Pipeline()
    invoker_train_pipeline.set_steps([(RunTraining(config), RunTraining.NAME, RunTraining.VERSION)])
    return invoker_train_pipeline


def create_posttrain_pipeline(config: Dict[str, Any]) -> Pipeline:
    """Construct pipeline for post-training LLM report generation and diagnostics.

    Args:
        config (Dict[str, Any]): Worker invoker configuration dictionary.

    Returns:
        Pipeline: Configured WPipe pipeline instance for post-train analysis.
    """
    invoker_posttrain_pipeline = Pipeline()
    invoker_posttrain_pipeline.set_steps([(LlmAnalizer(config), LlmAnalizer.NAME, LlmAnalizer.VERSION)])
    return invoker_posttrain_pipeline


def create_full_invoker_pipeline(config: Dict[str, Any]) -> Pipeline:
    """Construct complete multi-state invoker pipeline chaining EDA, training, and LLM analysis.

    Args:
        config (Dict[str, Any]): Worker invoker configuration dictionary.

    Returns:
        Pipeline: Unified WPipe pipeline instance.
    """
    invoker_full_pipeline = Pipeline()
    invoker_full_pipeline.set_steps(
        [
            (EDA(config), EDA.NAME, EDA.VERSION),
            (RunTraining(config), RunTraining.NAME, RunTraining.VERSION),
            (LlmAnalizer(config), LlmAnalizer.NAME, LlmAnalizer.VERSION),
        ]
    )
    return invoker_full_pipeline
