#!/bin/bash
# Installer for Worker Invoker (Production Version with Docker Compose)
# Author: William Rodríguez - wisrovi

# --- 1. DETECCIÓN Y PREPARACIÓN ---
IP_SUGERIDA=$(hostname -I | awk '{print $1}')

echo "-------------------------------------------------------"
echo "  Instalación de Worker Invoker para Train Service"
echo "-------------------------------------------------------"

# --- 2. PREPARACIÓN DE DIRECTORIOS ---
sudo mkdir -p /home/wisrovi/scripts/
sudo mkdir -p /etc/default/

# --- 3. CONFIGURACIÓN DE VARIABLES DE INSTANCIA ---
# Solo guardamos el nombre del worker, la IP vendrá de control_host.env
echo "WORKER_NAME=$(hostname -I | awk '{print $1}')" | sudo tee /etc/default/worker_invoker > /dev/null

# --- 4. GENERACIÓN DE USER.ENV (METADATOS DEL SISTEMA) ---
echo "Generando metadatos del sistema (user.env)..."
USER_ENV="/home/wisrovi/scripts/user.env"

{
    echo "USER=$(whoami)"
    echo "TZ=Europe/Madrid"
    echo "WORKER_HOST=$(hostname -I | awk '{print $1}')"
    echo "WORKER_HOSTNAME=$(hostname)"
    echo "WORKER_OS=$(uname -s)"
    echo "WORKER_KERNEL_VERSION=$(uname -r)"
    echo "WORKER_CPU_CORES=$(nproc)"
    echo "WORKER_GATEWAY=$(ip route | grep default | awk '{print $3}')"
    echo "WORKER_NETWORK_INTERFACE=$(ip route | grep default | awk '{print $5}')"
    echo "WORKER_DOCKER_VERSION=$(docker --version | awk '{print $3}' | sed 's/,//')"
    echo "WORKER_APP_BASE_PATH=/home/wisrovi/scripts"
    echo "WORKER_APP_ENV=production"
    echo "WORKER_HOME_DIR=$HOME"
    echo "WORKER_CURRENT_DATE=$(date '+%Y-%m-%d')"
    echo "WORKER_CURRENT_TIME=$(date '+%H:%M:%S')"
    
    # Información de GPU
    if command -v nvidia-smi &> /dev/null; then
        echo "WORKER_GPU_COUNT=$(nvidia-smi --query-gpu=count --format=csv,noheader)"
        echo "WORKER_GPU_MODEL=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1)"
        echo "WORKER_GPU_MEMORY=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -n 1)"
    else
        echo "WORKER_GPU_COUNT=0"
        echo "WORKER_GPU_MODEL=none"
        echo "WORKER_GPU_MEMORY=0"
    fi

    # Información de RAM
    MEM_TOTAL=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
    echo "WORKER_RAM_MEMORY=$((MEM_TOTAL / 1048576 * 8 / 10))g"
    echo "WORKER_CPU_CORES_AVAILABLE=$(( $(nproc) - 1 )).0"
} | sudo tee "$USER_ENV" > /dev/null

# --- 5. DESPLIEGUE DE ARCHIVOS ---
echo "Verificando configuración de red (control_host.env)..."

# Función para verificar si un archivo existe y no está vacío
is_valid_env() {
    [ -s "$1" ]
}

TARGET_ENV="/home/wisrovi/scripts/control_host.env"

if is_valid_env "../control_host.env"; then
    echo "Usando control_host.env de la raíz."
    sudo cp ../control_host.env "$TARGET_ENV"
elif is_valid_env "./control_host.env"; then
    echo "Usando control_host.env local."
    sudo cp ./control_host.env "$TARGET_ENV"
else
    echo "Aviso: control_host.env no encontrado o vacío. Iniciando configurador..."
    # Aseguramos que las dependencias estén instaladas
    echo "Verificando dependencias de sistema (python3-tk y customtkinter)..."
    sudo apt-get update -y && sudo apt-get install -y python3-tk
    pip3 install customtkinter --quiet --break-system-packages
    
    # Intentamos ejecutar el configurador. 
    # Si falla (por falta de X11), el usuario deberá crearlo manualmente.
    if python3 config.py; then
        if is_valid_env "./control_host.env"; then
            sudo cp ./control_host.env "$TARGET_ENV"
        else
            echo "Error: El configurador terminó pero no se generó control_host.env."
            exit 1
        fi
    else
        echo "Error: No se pudo ejecutar el configurador (config.py). ¿Está instalado customtkinter?"
        exit 1
    fi
fi

echo "Copiando scripts y configuraciones a /home/wisrovi/scripts/..."
sudo cp launcher_invoker.sh /home/wisrovi/scripts/launcher_worker.sh
sudo cp docker-compose.yaml /home/wisrovi/scripts/docker-compose.yaml

# Copiar archivo de unidad de sistema
sudo cp worker_invoker@.service /etc/systemd/system/

# Dar permisos de ejecución al launcher
sudo chmod +x /home/wisrovi/scripts/launcher_worker.sh

# --- 5. ACTIVACIÓN DEL SERVICIO ---
sudo systemctl daemon-reload

WORKER_INSTANCE=$(hostname -I | awk '{print $1}')
echo "Habilitando servicio: worker_invoker@${WORKER_INSTANCE}"
sudo systemctl enable "worker_invoker@${WORKER_INSTANCE}"
sudo systemctl restart "worker_invoker@${WORKER_INSTANCE}"

# Intentamos obtener la IP del CONTROL_HOST para el resumen final
CH_IP=$(grep "CONTROL_HOST=" /home/wisrovi/scripts/control_host.env | cut -d'=' -f2)

echo "-------------------------------------------------------"
echo "¡Instalación completada con éxito!"
echo "Servicio: worker_invoker@${WORKER_INSTANCE}"
echo "Directorio de trabajo: /home/wisrovi/scripts/"
echo "Servidor de Control (IP): ${CH_IP:-No configurada}"
echo "-------------------------------------------------------"
