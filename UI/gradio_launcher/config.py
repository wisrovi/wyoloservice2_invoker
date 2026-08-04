import os
import yaml

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

def load_ui_config() -> dict:
    """Loads configuration options from config.yaml."""
    if not os.path.exists(CONFIG_PATH):
        return {
            "run_full_pipeline": True,
            "theme": "soft",
            "default_task_type": "classification",
        }
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {
        "run_full_pipeline": True,
        "theme": "soft",
        "default_task_type": "classification",
    }

# Load options on module load
_options = load_ui_config()

RUN_FULL_PIPELINE = bool(_options.get("run_full_pipeline", True))
THEME_NAME = str(_options.get("theme", "soft"))
DEFAULT_TASK_TYPE = str(_options.get("default_task_type", "classification"))
