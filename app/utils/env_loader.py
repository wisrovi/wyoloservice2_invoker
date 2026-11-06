"""Environment variable loader utilities for Invoker."""

import os


# pylint: disable=broad-exception-caught
def load_env_file(path: str) -> dict[str, str]:
    """Parse key-value pairs from an environment file safely.

    Args:
        path (str): Filesystem path to the environment file.

    Returns:
        Dict[str, str]: Dictionary containing parsed environment variables.
    """
    envs: dict[str, str] = {}
    if not os.path.exists(path):
        return envs

    try:
        with open(path, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line and not line.startswith("#"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        val = parts[1].strip()
                        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                            val = val[1:-1]
                        envs[parts[0].strip()] = val
    except Exception as exc:
        print(f"--- [INVOKER] Warning: Error reading env file {path}: {exc} ---")
    return envs
