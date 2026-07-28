#!/bin/bash
# Script to pause public Celery queues (gpus_high, gpus_medium, gpus_low) only for this worker
# Author: William Rodriguez - wisrovi

CONTAINER_NAME=$(docker ps --filter "name=wyolo_invoker" --format "{{.Names}}" | head -n 1)

if [ -z "$CONTAINER_NAME" ]; then
    echo "[-] Error: No running wyolo_invoker container found."
    exit 1
fi

NODE_NAME="celery@$(docker exec "$CONTAINER_NAME" hostname)"

echo "[*] Found active container: $CONTAINER_NAME"
echo "[*] Target Celery node: $NODE_NAME"
echo "[*] Pausing public queues (gpus_high, gpus_medium, gpus_low)..."

docker exec "$CONTAINER_NAME" celery -A worker_gpu control -d "$NODE_NAME" cancel_consumer gpus_high
docker exec "$CONTAINER_NAME" celery -A worker_gpu control -d "$NODE_NAME" cancel_consumer gpus_medium
docker exec "$CONTAINER_NAME" celery -A worker_gpu control -d "$NODE_NAME" cancel_consumer gpus_low

echo "[+] Public queues paused successfully. Worker '$NODE_NAME' is now ONLY listening to its private queue."
