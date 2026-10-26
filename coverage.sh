#!/bin/bash
# Calculates test coverage inside a Docker container
echo "Calculating test coverage in Docker container..."
docker run --rm -e PYTHONPATH=/app/app:/app -v "$(pwd):/app" -w /app python:3.10-slim bash -c "pip install pytest pytest-cov requests pyyaml redis docker rich && pytest --cov=app --cov-report=term-missing tests/"
