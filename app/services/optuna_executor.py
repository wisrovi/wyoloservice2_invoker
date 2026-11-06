"""Optuna hyperparameter optimization execution service for worker invoker."""

import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict, Optional
import optuna


def suggest_from_space(trial: optuna.trial.Trial, search_space: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """Suggest hyperparameters from defined search space specification.

    Args:
        trial (optuna.trial.Trial): Current Optuna trial instance.
        search_space (Dict[str, Any]): Search space bounds and distributions.
        prefix (str): Namespace prefix for nested parameter names.

    Returns:
        Dict[str, Any]: Mapping of parameter names to sampled values.
    """
    suggested: Dict[str, Any] = {}
    for key, val in search_space.items():
        param_name = f"{prefix}{key}"
        if isinstance(val, dict):
            suggested[key] = suggest_from_space(trial, val, prefix=f"{param_name}:")
        elif isinstance(val, list) and len(val) >= 2:
            dist_type = val[0]
            if dist_type == "choice":
                choices = val[1] if isinstance(val[1], list) else val[1:]
                suggested[key] = trial.suggest_categorical(param_name, choices)
            elif dist_type == "uniform" and len(val) >= 3:
                suggested[key] = trial.suggest_float(param_name, float(val[1]), float(val[2]))
            elif dist_type == "loguniform" and len(val) >= 3:
                suggested[key] = trial.suggest_float(param_name, float(val[1]), float(val[2]), log=True)
            elif dist_type == "intuniform" and len(val) >= 3:
                suggested[key] = trial.suggest_int(param_name, int(val[1]), int(val[2]))
    return suggested


def merge_configs(base: Dict[str, Any], suggested: Dict[str, Any]) -> Dict[str, Any]:
    """Merge suggested hyperparameter values into base training configuration.

    Args:
        base (Dict[str, Any]): Base configuration dictionary.
        suggested (Dict[str, Any]): Parameter updates to merge.

    Returns:
        Dict[str, Any]: Merged configuration dictionary.
    """
    for key, val in suggested.items():
        if isinstance(val, dict) and key in base and isinstance(base[key], dict):
            merge_configs(base[key], val)
        else:
            base[key] = val
    return base


class OptunaTrialObjective:
    """Callable trial evaluator executing training pipeline for Optuna studies."""

    def __init__(self, training_config: Dict[str, Any], search_space: Dict[str, Any], pipeline_runner: Any):
        """Initialize trial objective.

        Args:
            training_config (Dict[str, Any]): Base job configuration.
            search_space (Dict[str, Any]): Hyperparameter search space.
            pipeline_runner (Any): Pipeline executor instance.
        """
        self.training_config = training_config
        self.search_space = search_space
        self.pipeline_runner = pipeline_runner
        self.latest_accuracy: float = 0.0

    def __call__(self, trial: optuna.trial.Trial) -> float:
        """Evaluate trial execution and return target metric.

        Args:
            trial (optuna.trial.Trial): Current trial.

        Returns:
            float: Evaluated fitness/accuracy score.
        """
        trial_config = json.loads(json.dumps(self.training_config))
        if self.search_space:
            suggested = suggest_from_space(trial, self.search_space)
            trial_config = merge_configs(trial_config, suggested)

        result = self.pipeline_runner.run(trial_config)
        acc = float(result.get("accuracy", 0.0))
        self.latest_accuracy = acc
        return acc


def run_optuna_study(
    training_config: Dict[str, Any], config: Dict[str, Any], pipeline_runner: Any
) -> Dict[str, Any]:
    """Execute distributed Optuna study and return optimal parameters.

    Args:
        training_config (Dict[str, Any]): Job parameters dict.
        config (Dict[str, Any]): Invoker settings dict.
        pipeline_runner (Any): Training pipeline instance.

    Returns:
        Dict[str, Any]: Best parameters and evaluation score.
    """
    trials_count = training_config.get("n_trials", config.get("sweeper", {}).get("n_trials", 1))
    direction_str = training_config.get("direction", config.get("sweeper", {}).get("direction", "maximize"))
    sampler_name = training_config.get("sampler", config.get("sweeper", {}).get("sampler", "TPESampler"))
    search_space = training_config.get("sweeper", {}).get("search_space", {})

    base_name = training_config.get("sweeper", {}).get("study_name") or f"study_{datetime.now().strftime('%Y%m%d')}"
    space_hash = hashlib.md5(json.dumps(search_space, sort_keys=True).encode()).hexdigest()[:8]
    study_name = f"{base_name}_{space_hash}"

    control_host = os.getenv("CONTROL_HOST", "localhost")
    storage_url = f"postgresql://postgres:postgres@{control_host}:23436/optuna_db"

    sampler = (
        optuna.samplers.RandomSampler()
        if sampler_name == "RandomSampler"
        else (optuna.samplers.CmaEsSampler() if sampler_name == "CmaEsSampler" else optuna.samplers.TPESampler())
    )
    direction = (
        optuna.study.StudyDirection.MINIMIZE if direction_str == "minimize" else optuna.study.StudyDirection.MAXIMIZE
    )

    study = optuna.create_study(
        study_name=study_name, direction=direction, sampler=sampler, storage=storage_url, load_if_exists=True
    )
    objective = OptunaTrialObjective(training_config, search_space, pipeline_runner)
    study.optimize(objective, n_trials=trials_count, show_progress_bar=True)

    try:
        best_val = float(study.best_value)
    except (ValueError, TypeError):
        best_val = objective.latest_accuracy

    res = dict(study.best_params)
    res["accuracy"] = best_val
    res["fitness"] = best_val
    return res
