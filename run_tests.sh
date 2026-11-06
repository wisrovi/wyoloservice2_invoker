#!/bin/bash
# Runs pytest inside a Docker container enforcing 0 bytecode artifacts
echo "Running tests in Docker container..."
docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/app/app:/app -v "$(pwd):/app" -w /app python:3.10-slim bash -c "pip install pytest requests pyyaml redis docker rich pydantic && pytest tests/ app/tests/"
