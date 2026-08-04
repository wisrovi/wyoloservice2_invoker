import sys
import os

# Ensure UI directory is in path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import styles
from ui.layout import build_layout

# Build layout
demo = build_layout()

# Run application
if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        head=styles._JS_SHORTCUTS,
        allowed_paths=["/results"],
    )
