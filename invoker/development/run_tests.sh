#!/bin/bash
# Script to run tests inside a Docker container
# This ensures a clean and consistent testing environment.

IMAGE_NAME="worker-test-env"

# Build a temporary image for testing
docker build -t $IMAGE_NAME -f - . <<EOF
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt pytest pytest-cov
COPY . .
ENV PYTHONPATH=/app
CMD ["pytest", "tests/"]
EOF

# Run the tests
docker run --rm $IMAGE_NAME
