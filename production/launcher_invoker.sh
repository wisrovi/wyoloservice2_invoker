#!/bin/bash
# Launcher script for Worker Invoker using Docker Compose
# Author: William Rodriguez - wisrovi

# --- 1. CONFIGURATION ---
# Variables inherited from Systemd (EnvironmentFile=/etc/default/worker_invoker)
DEFAULT_IP=$(hostname -I | awk '{print $1}')
export WORKER_NAME=${WORKER_NAME:-$DEFAULT_IP}

# Process parameters (optional for manual overrides)
while [[ $# -gt 0 ]]; do
  case $1 in
    -n|--private_name)
      export WORKER_NAME="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Generate random CPU affinity if it doesn't exist
if [ -z "$CORE_ASSIGNED" ]; then
    export CORE_ASSIGNED=$((RANDOM % $(nproc)))
fi

echo "Starting Worker Invoker Stack for: $WORKER_NAME"
echo "Assigned core: $CORE_ASSIGNED"

# --- 2. EXECUTION ---
# Enter the directory where docker-compose.yaml is located
cd /home/wisrovi/scripts/ || exit

# Clean previous containers if they exist with the same project name
# Use the worker name as project name to avoid collisions
PROJECT_NAME="invoker_${WORKER_NAME//./_}"

# Re-create network if it doesn't exist (silent)
docker network create train_service 2>/dev/null || true

# Execute compose
# --remove-orphans to clean services no longer in the yaml
# No -d so Systemd can monitor the process
docker-compose -p "$PROJECT_NAME" up --remove-orphans
