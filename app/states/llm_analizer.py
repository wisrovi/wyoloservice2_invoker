# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""LLM Analyzer State Module.

This module provides the LlmAnalizer class for post-training analysis using LLMs.
"""

from typing import Any, Dict
from utils.training_report_analyzer import TrainingReportAnalyzer


class LlmAnalizer:
    """State class for performing post-training analysis with LLMs."""

    NAME: str = "LLMAnalizer"
    VERSION: str = "1.0.0"

    def __init__(self, config: dict[str, Any]):
        """Initialize LLM Analyzer with configuration.

        Args:
            config: Worker configuration dictionary.
        """
        self.config = config

    def __call__(self, training_config: dict[str, Any]) -> dict[str, Any]:
        """Execute LLM analysis process.

        Args:
            training_config: Training configuration and results.

        Returns:
            Dict[str, Any]: Analysis results.
        """
        print(f"--- [STATE:{self.NAME}] Running LLM Analysis... ---")
        results_file = "/home/wyolo/train_service_results/evaluation_metrics/results.csv"

        try:
            report = TrainingReportAnalyzer().analyze(results_file)
            return {
                "status": "success",
                "llm_report": report,
            }
        except Exception as exc:
            print(f"LLM Analyzer failed: {exc}")
            return {
                "status": "failed",
                "llm_report": "",
                "error": str(exc),
            }
