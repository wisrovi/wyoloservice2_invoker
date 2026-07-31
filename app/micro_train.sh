#!/bin/bash
# Docker run command for testing/debugging the executor container from inside the invoker container
# Usage: micro_train [-d] [--bash] --config "/wyolo/worker/request/config_train.yaml"
#   -d:      Run in detached mode (daemon). Default: foreground with auto-remove.
#   --bash:  Keep container alive with zsh for debugging.

set -euo pipefail

# Configuration and defaults
CONFIG_FILE="/wyolo/worker/request/config_train.yaml"
DETACHED=false
BASH_MODE=false
GPU_PERCENT="60"
CPU_CORES="4"
RAM_GB="8"
SHM_GB="12"

# Samba credentials (pointing to the central control host)
CONTROL_HOST="${CONTROL_HOST:-192.168.10.252}"
CIFS_USER="${CIFS_USER:-wisrovi}"
CIFS_PASS="${CIFS_PASS:-wyoloservice}"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -d)
            DETACHED=true
            shift
            ;;
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --bash)
            BASH_MODE=true
            shift
            ;;
        --gpu)
            GPU_PERCENT="$2"
            shift 2
            ;;
        --cpu)
            CPU_CORES="$2"
            shift 2
            ;;
        --ram)
            RAM_GB="$2"
            shift 2
            ;;
        --shm)
            SHM_GB="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Usage: $0 [-d] [--bash] --config <config_file_path> [--gpu <%>] [--cpu <cores>] [--ram <GB>] [--shm <GB>]" >&2
            exit 1
            ;;
    esac
done

# Path resolution, automatic copy, and validation inside the invoker container
if [[ "$BASH_MODE" == false ]]; then
    # Check if the configuration path is external to the expected directory (/wyolo/worker/request/)
    # We skip checks for /examples/ since those are inside the executor container
    if [[ "$CONFIG_FILE" != /wyolo/worker/request/* && "$CONFIG_FILE" != /examples/* ]]; then
        if [[ ! -f "$CONFIG_FILE" ]]; then
            echo "ERROR: Config file not found: $CONFIG_FILE" >&2
            exit 1
        fi
        
        FILENAME=$(basename "$CONFIG_FILE")
        TARGET_HOST_PATH="/wyolo/worker/request/$FILENAME"
        
        echo "[INVOKER] Copying external config $CONFIG_FILE to $TARGET_HOST_PATH"
        cp "$CONFIG_FILE" "$TARGET_HOST_PATH"
        chmod 666 "$TARGET_HOST_PATH"
        
        # Update CONFIG_FILE variable to point to the location inside the container mapping
        CONFIG_FILE="$TARGET_HOST_PATH"
    fi

    # Determine validation path (for the invoker context, paths under /wyolo/worker/request/ are local)
    if [[ "$CONFIG_FILE" == /wyolo/worker/request/* ]]; then
        HOST_CONFIG="$CONFIG_FILE"
    elif [[ "$CONFIG_FILE" == /examples/* ]]; then
        # It's an internal path, we don't need to validate it
        HOST_CONFIG=""
    else
        HOST_CONFIG="$CONFIG_FILE"
    fi

    # Validate config file exists locally
    if [[ -n "$HOST_CONFIG" && ! -f "$HOST_CONFIG" ]]; then
        echo "ERROR: Config file not found: $HOST_CONFIG" >&2
        exit 1
    fi
fi

# Convert to executor container path for the --file argument
if [[ "$CONFIG_FILE" == /wyolo/worker/request/* ]]; then
    CONTAINER_CONFIG="$CONFIG_FILE"
elif [[ "$CONFIG_FILE" == /examples/* ]]; then
    CONTAINER_CONFIG="$CONFIG_FILE"
else
    CONTAINER_CONFIG="/wyolo/worker/request/$(basename "$CONFIG_FILE")"
fi

# Build docker run arguments based on execution mode
if [[ "$DETACHED" == true ]]; then
    DOCKER_RUN_ARGS=(-d --name wyolo_executor_test)
else
    if [[ -t 0 ]]; then
        DOCKER_RUN_ARGS=(--rm -it --name wyolo_executor_test)
    else
        DOCKER_RUN_ARGS=(--rm -i --name wyolo_executor_test)
    fi
fi

# Define execution command based on debugging mode
if [[ "$BASH_MODE" == true ]]; then
    DETACHED=false
    CMD="zsh"
    DOCKER_RUN_ARGS=(--rm -it --name wyolo_executor_test)
else
    CMD="nvidia-smi && echo \"[EXECUTOR] Starting mount...\" && /usr/local/bin/mount-cifs.sh && echo \"[EXECUTOR] Mount OK. Starting training...\" && python main.py --file \"$CONTAINER_CONFIG\""
fi

# Execute Docker container (communicating via mapped socket to host Docker daemon)
# Note: Host paths are used for volume mapping since the host Docker daemon handles it.
docker run "${DOCKER_RUN_ARGS[@]}" \
  --pull missing \
  --hostname default_user \
  --privileged \
  --network host \
  --shm-size=${SHM_GB}g \
  --cpus=${CPU_CORES} \
  --memory=${RAM_GB}g \
  --cap-add=SYS_ADMIN \
  --cap-add=DAC_READ_SEARCH \
  --cap-add=NET_ADMIN \
  --cap-add=SYS_RESOURCE \
  --gpus '"device=0"' \
  -e NVIDIA_VISIBLE_DEVICES=0 \
  -e NVIDIA_DRIVER_CAPABILITIES=all \
  -e TZ=Europe/Madrid \
  -e PYTHONUNBUFFERED=1 \
  -e MAX_GPU="$GPU_PERCENT" \
  -e WORKER_CPU_CORES="$CPU_CORES" \
  -e WORKER_RAM_MEMORY="${RAM_GB}g" \
  -e WORKER_SHM_MEMORY="${SHM_GB}g" \
  -e CONTROL_HOST="$CONTROL_HOST" \
  -e CIFS_USER="$CIFS_USER" \
  -e CIFS_PASS="$CIFS_PASS" \
  -v /home/wyolo/events:/wyolo/worker/events:rw \
  -v /home/wyolo/train_service_results:/wyolo/worker/train_service_results:rw \
  -v /home/wyolo/request:/wyolo/worker/request:rw \
  wisrovi/train_service:worker_executor_v1.0.0 \
  bash -c "$CMD"
