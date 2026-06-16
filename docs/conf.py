# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Docstring."""

import os
import sys

sys.path.insert(0, os.path.abspath(".."))

project = "GPU Invoker (Hive Worker)"
copyright = "2026, William Steve Rodriguez Villamizar (wisrovi)"
author = "William Steve Rodriguez Villamizar (wisrovi)"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_copybutton",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "furo"
html_static_path = ["_static"]
