"""Timeout and watchdog calculations for training sessions."""

from typing import Any, Dict, Optional

DEFAULT_REFERENCE_TIME_HOURS: float = 12.0
POST_TRAIN_MARGIN_RATIO: float = 0.30
MIN_POST_TRAIN_MARGIN_SECONDS: int = 2700
DEFAULT_REDIS_TTL_SECONDS: int = 86400


def parse_user_train_time_hours(training_config: Optional[Dict[str, Any]]) -> Optional[float]:
    """Extract a valid user-defined training time limit in hours.

    Args:
        training_config (Optional[Dict[str, Any]]): Job configuration dictionary.

    Returns:
        Optional[float]: Time in hours if valid and > 0, None otherwise.
    """
    if not isinstance(training_config, dict):
        return None
    train_section = training_config.get("train")
    if not isinstance(train_section, dict):
        return None
    raw_time = train_section.get("time")
    if raw_time is None or isinstance(raw_time, bool):
        return None
    try:
        parsed = float(raw_time)
        return parsed if parsed > 0.0 else None
    except (ValueError, TypeError):
        return None


def resolve_training_timeouts(
    training_config: Optional[Dict[str, Any]] = None,
    invoker_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve cascading timeouts (Ultralytics 1.0x, Invoker 1.3x, Redis 2.0x).

    Args:
        training_config (Optional[Dict[str, Any]]): Job parameters.
        invoker_config (Optional[Dict[str, Any]]): Invoker settings.

    Returns:
        Dict[str, Any]: Mapping of timeout parameters including timeout_seconds and redis_ttl_seconds.
    """
    t_cfg = training_config if isinstance(training_config, dict) else {}
    i_cfg = invoker_config if isinstance(invoker_config, dict) else {}

    user_time_hours = parse_user_train_time_hours(t_cfg)
    ref_hours = user_time_hours if user_time_hours is not None else DEFAULT_REFERENCE_TIME_HOURS

    base_seconds = int(ref_hours * 3600)
    margin_seconds = max(int(base_seconds * POST_TRAIN_MARGIN_RATIO), MIN_POST_TRAIN_MARGIN_SECONDS)
    calculated_timeout = base_seconds + margin_seconds

    if "executor_timeout_seconds" in t_cfg and t_cfg["executor_timeout_seconds"] is not None:
        timeout_seconds = int(t_cfg["executor_timeout_seconds"])
    elif (
        user_time_hours is None
        and "executor_timeout_seconds" in i_cfg
        and i_cfg["executor_timeout_seconds"] is not None
        and int(i_cfg["executor_timeout_seconds"]) != 43200
    ):
        timeout_seconds = int(i_cfg["executor_timeout_seconds"])
    else:
        timeout_seconds = calculated_timeout

    redis_ttl_seconds = max(DEFAULT_REDIS_TTL_SECONDS, int(ref_hours * 3600 * 2))

    return {
        "user_time_hours": user_time_hours,
        "ref_hours": ref_hours,
        "base_seconds": base_seconds,
        "margin_seconds": margin_seconds,
        "timeout_seconds": timeout_seconds,
        "redis_ttl_seconds": redis_ttl_seconds,
    }
