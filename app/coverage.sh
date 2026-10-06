#!/bin/bash
# Script to calculate code coverage using pytest-cov inside Docker.

IMAGE_NAME="worker-test-env"

docker run --rm $IMAGE_NAME pytest --cov=states --cov=utils tests/ --cov-report=term-missing
