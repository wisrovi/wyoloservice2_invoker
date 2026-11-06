#!/bin/bash
# Runs pytest coverage inside a Docker container enforcing 0 bytecode artifacts
echo "Calculating test coverage in Docker container..."
docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/app/app:/app -v "$(pwd):/app" -w /app python:3.10-slim bash -c "pip install pytest pytest-cov requests pyyaml redis docker rich pydantic && pytest --cov=app tests/ app/tests/"
