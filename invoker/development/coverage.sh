#!/bin/bash
# Script to calculate code coverage using pytest-cov.

echo "Calculating code coverage..."

# Ensure we are in the right directory and have PYTHONPATH set
export PYTHONPATH=$PYTHONPATH:$(pwd)

pytest --cov=states --cov=worker_gpu tests/ --cov-report=term-missing
