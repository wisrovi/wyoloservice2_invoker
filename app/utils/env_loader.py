"""Environment variable loader utilities for Invoker."""

import os
from typing import Dict


def load_env_file(path: str) -> Dict[str, str]:
    """Parse key-value pairs from an environment file safely.

    Args:
        path (str): Filesystem path to the environment file.

    Returns:
        Dict[str, str]: Dictionary containing parsed environment variables.
    """
    envs: Dict[str, str] = {}
    if not os.path.exists(path):
        return envs

    try:
        with open(path, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line and not line.startswith("#"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        envs[parts[0].strip()] = parts[1].strip()
    except Exception as exc:
        print(f"--- [INVOKER] Warning: Error reading env file {path}: {exc} ---")
    return envs
