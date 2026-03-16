#!/bin/bash
# Launcher script for Worker Invoker - Fixed Logic
# Name: William Rodríguez - wisrovi

# --- 1. CONFIGURACIÓN ---
DEFAULT_IP=$(hostname -I | awk '{print $1}')
WORKER_NAME=""
REDIS_HOST="localhost:23437"
REDIS_URL="redis://${REDIS_HOST}/0"
HISTORY_FILE="train_service_history.md"


# Un solo bucle para procesar todos los parámetros
while [[ $# -gt 0 ]]; do
  case $1 in
    -n|--private_name)
      WORKER_NAME="$2"
      shift 2
      ;;
    -r|--redis_host)
      REDIS_HOST="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Asignación de valores por defecto tras procesar parámetros
[[ -z "$REDIS_HOST" ]] && REDIS_HOST=$DEFAULT_IP
[[ -z "$WORKER_NAME" ]] && WORKER_NAME=$DEFAULT_IP

REDIS_URL="redis://${REDIS_HOST}/0"
CONTAINER_NAME="worker_${WORKER_NAME}"

# --- 2. COMANDOS DE DEFINICIÓN ---
CMD_AUTOHEAL="docker run -d --name autoheal --restart always -v /var/run/docker.sock:/var/run/docker.sock -e AUTOHEAL_INTERVAL=10 -e CURL_TIMEOUT=30 -e AUTOHEAL_CONTAINER_LABEL=all willfarrell/autoheal"
CMD_WATCHTOWER="docker run -d --name watchtower --restart always -v /var/run/docker.sock:/var/run/docker.sock -e WATCHTOWER_LABEL_ENABLE=true -e WATCHTOWER_SCHEDULE='0 0 0,2,4,6,8,10,12,14,16,18,20,22 * * *' -e WATCHTOWER_CLEANUP=true --label 'com.centurylinklabs.watchtower.enable=false' containrrr/watchtower"

deploy_worker() {
    CORE_ASSIGNED=$((RANDOM % $(nproc)))
    echo "Ejecutando deploy_worker en core $CORE_ASSIGNED..."
    docker run -d \
      --restart always \
      --hostname "${CONTAINER_NAME}" \
      --name "${CONTAINER_NAME}" \
      --label "autoheal=true" \
      --label "com.centurylinklabs.watchtower.enable=true" \
      --cpus="1.0" \
      --cpuset-cpus="$CORE_ASSIGNED" \
      --memory="300m" \
      --log-opt max-size=10m \
      --log-opt max-file=3 \
      --health-cmd="celery -A worker_gpu inspect ping -d celery@${CONTAINER_NAME}" \
      --health-interval=30s \
      -e REDIS_URL="${REDIS_URL}" \
      -e PRIVATE_QUEUE="${WORKER_NAME}" \
      wisrovi/train_service:worker_invoker_v1.0.0 \
      celery -A worker_gpu worker -Q "${WORKER_NAME},gpus_high,gpus_medium,gpus_low" --loglevel=info --concurrency=1 --prefetch-multiplier=1 -Ofair --max-tasks-per-child=1 --max-memory-per-child=250000 --without-gossip --without-mingle --without-heartbeat
}

# --- 3. FUNCIÓN DE VALIDACIÓN CORREGIDA ---
ensure_container_alive() {
    local name=$1
    local cmd=$2

    # Verificamos si el contenedor existe (corriendo o no)
    if ! docker ps -a --format '{{.Names}}' | grep -Eq "^${name}\$"; then
        echo "[$(date)] $name no existe. Creando con docker run..."
        eval "$cmd"
    else
        # Si existe, verificamos si está corriendo
        local state=$(docker inspect -f '{{.State.Running}}' "${name}")
        if [ "$state" != "true" ]; then
            echo "[$(date)] $name existe pero está detenido. Iniciando con docker start..."
            docker start "$name"
        fi
    fi
}

# --- 4. BUCLE INFINITO ---
echo "Iniciando Watchdog Total para: $CONTAINER_NAME, autoheal y watchtower"

while true; do
    ensure_container_alive "autoheal" "$CMD_AUTOHEAL"
    ensure_container_alive "watchtower" "$CMD_WATCHTOWER"
    ensure_container_alive "$CONTAINER_NAME" "deploy_worker"

    sleep 60
done