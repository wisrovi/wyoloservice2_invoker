# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Exploratory Data Analysis (EDA) State Module.

This module provides the EDA class for performing initial data analysis before training.
"""

from typing import Any, Dict
from utils.dataset_analyzer import DatasetAnalyzer


class EDA:
    """State class for performing Exploratory Data Analysis."""

    NAME: str = "EDA"
    VERSION: str = "1.0.0"

    def __init__(self, config: dict[str, Any]):
        """Initialize EDA with configuration.

        Args:
            config: Worker configuration dictionary.
        """
        self.config = config

    def __call__(self, training_config: dict[str, Any]) -> dict[str, Any]:
        """Execute EDA process.

        Args:
            training_config: Training configuration.

        Returns:
            Dict[str, Any]: Results of the EDA.
        """
        print(f"--- [STATE:{self.NAME}] Running EDA... ---")
        dataset_path = training_config.get("train", {}).get("data")

        if not dataset_path:
            print("EDA skipped: dataset path not found")
            return {
                "status": "success",
                "eda_results": {},
            }

        try:
            eda_results = DatasetAnalyzer().analyze(dataset_path)
            return {
                "status": "success",
                "eda_results": eda_results,
            }
        except Exception as exc:
            print(f"EDA failed: {exc}")
            return {
                "status": "success",
                "eda_results": {},
                "eda_error": str(exc),
            }
