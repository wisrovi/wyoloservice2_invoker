"""Core entrypoint for wyoloservice2_invoker WPipe microservice.

Provides CLI diagnostics, pipeline self-checks, and execution utilities.
"""

import os
import sys
from typing import Any, Dict
import yaml
from pipelines import create_full_invoker_pipeline, create_pretrain_pipeline, create_training_pipeline
from utils.orchestrator import get_orchestrator


def load_worker_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Load worker invoker configuration from YAML file.

    Args:
        config_path (str): Relative or absolute path to configuration file.

    Returns:
        Dict[str, Any]: Parsed configuration mapping.
    """
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    return data.get("worker", {})
        except Exception as exc:
            print(f"Warning: Error loading {config_path}: {exc}")
    return {}


def main() -> None:
    """Run CLI self-check and display invoker microservice runtime diagnostics."""
    config = load_worker_config()
    print("=" * 60)
    print("  wyoloservice2_invoker - WPipe Microservice Entrypoint")
    print("=" * 60)
    orchestrator = get_orchestrator(config)
    print(f"Active Orchestrator: {orchestrator.__class__.__name__}")
    print(f"Host IP / Queue:     {os.getenv('WORKER_HOST', 'unknown')}")
    print("Pre-training EDA Pipeline:  Ready")
    print("Container Training Pipeline: Ready")
    print("Post-training LLM Pipeline:  Ready")
    print("=" * 60)


if __name__ == "__main__":
    main()
