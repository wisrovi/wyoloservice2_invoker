#!/bin/bash
# Launcher script for Worker Invoker using Docker Compose
# Author: William Rodríguez - wisrovi

# --- 1. CONFIGURACIÓN ---
# Variables heredadas de Systemd (EnvironmentFile=/etc/default/worker_invoker)
DEFAULT_IP=$(hostname -I | awk '{print $1}')
export WORKER_NAME=${WORKER_NAME:-$DEFAULT_IP}

# Procesar parámetros (opcional para overrides manuales)
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

# Generar afinidad de CPU aleatoria si no existe
if [ -z "$CORE_ASSIGNED" ]; then
    export CORE_ASSIGNED=$((RANDOM % $(nproc)))
fi

echo "Iniciando Worker Invoker Stack para: $WORKER_NAME"
echo "Redis Host: $REDIS_HOST"
echo "Core asignado: $CORE_ASSIGNED"

# --- 2. EJECUCIÓN ---
# Entramos al directorio donde está el docker-compose.yaml
cd /home/wisrovi/scripts/

# Limpiar contenedores previos si existieran con el mismo nombre de proyecto
# Usamos el nombre del worker como nombre de proyecto para evitar colisiones
PROJECT_NAME="invoker_${WORKER_NAME//./_}"

# Ejecutar compose
# --remove-orphans para limpiar servicios que ya no estén en el yaml
# Sin -d para que Systemd pueda monitorear el proceso
docker network create train_service
docker-compose -p "$PROJECT_NAME" up --remove-orphans
