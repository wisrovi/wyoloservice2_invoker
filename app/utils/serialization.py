"""Data serialization utilities for Invoker without dynamic reflection."""

from typing import Any, Dict, List
from pydantic import BaseModel


def make_serializable(data: Any) -> Any:
    """Recursively convert nested data structures into JSON/YAML serializable primitives.

    Args:
        data (Any): Arbitrary object, dictionary, list, or primitive.

    Returns:
        Any: Clean data structure composed exclusively of primitive types.
    """
    if isinstance(data, dict):
        return {str(k): make_serializable(v) for k, v in data.items() if not str(k).startswith("_")}
    if isinstance(data, list):
        return [make_serializable(v) for v in data]
    if isinstance(data, (str, int, float, bool, type(None))):
        return data
    if isinstance(data, BaseModel):
        return make_serializable(data.model_dump())
    return str(data)
