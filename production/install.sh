#!/bin/bash
# Installer for Worker Invoker (Production Version with Docker Compose)
# Author: William Rodriguez - wisrovi

# --- 1. PREPARATION ---
echo "-------------------------------------------------------"
echo "  Installing Worker Invoker for Train Service"
echo "-------------------------------------------------------"

# --- 2. DIRECTORY PREPARATION ---
sudo mkdir -p /home/wisrovi/scripts/
sudo mkdir -p /etc/default/

# --- 3. INSTANCE VARIABLE CONFIGURATION ---
WORKER_IP=$(hostname -I | awk '{print $1}')
echo "WORKER_NAME=$WORKER_IP" | sudo tee /etc/default/worker_invoker > /dev/null

# --- 4. USER.ENV GENERATION (SYSTEM METADATA) ---
echo "Generating system metadata (user.env)..."
USER_ENV="/home/wisrovi/scripts/user.env"

{
    echo "USER=$(whoami)"
    echo "TZ=Europe/Madrid"
    echo "WORKER_HOST=$WORKER_IP"
    echo "WORKER_HOSTNAME=$(hostname)"
    echo "WORKER_OS=$(uname -s)"
    echo "WORKER_KERNEL_VERSION=$(uname -r)"
    echo "WORKER_CPU_CORES=$(nproc)"
    echo "WORKER_GATEWAY=$(ip route | grep default | awk '{print $3}' | head -n 1)"
    echo "WORKER_NETWORK_INTERFACE=$(ip route | grep default | awk '{print $5}' | head -n 1)"
    echo "WORKER_DOCKER_VERSION=$(docker --version | awk '{print $3}' | sed 's/,//')"
    echo "WORKER_APP_BASE_PATH=/home/wisrovi/scripts"
    echo "WORKER_APP_ENV=production"
    echo "WORKER_HOME_DIR=$HOME"
    echo "WORKER_CURRENT_DATE=$(date '+%Y-%m-%d')"
    echo "WORKER_CURRENT_TIME=$(date '+%H:%M:%S')"

    # GPU Information
    if command -v nvidia-smi &> /dev/null; then
        echo "WORKER_GPU_COUNT=$(nvidia-smi --query-gpu=count --format=csv,noheader | head -n 1)"
        echo "WORKER_GPU_MODEL=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1)"
        echo "WORKER_GPU_MEMORY=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -n 1)"
    else
        echo "WORKER_GPU_COUNT=0"
        echo "WORKER_GPU_MODEL=none"
        echo "WORKER_GPU_MEMORY=0"
    fi

    # RAM Information
    MEM_TOTAL=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
    # Increase precision: MEM_TOTAL * 8 / 10 / 1024^2 (to get GB)
    echo "WORKER_RAM_MEMORY=$((MEM_TOTAL * 8 / 10 / 1048576))g"
    echo "WORKER_CPU_CORES_AVAILABLE=$(( $(nproc) - 1 )).0"
} | sudo tee "$USER_ENV" > /dev/null

# --- 5. FILE DEPLOYMENT ---
TARGET_ENV="/home/wisrovi/scripts/control_host.env"

# Function to verify if a file exists and is not empty
is_valid_env() {
    [ -s "$1" ]
}

if is_valid_env "../control_host.env"; then
    echo "Using control_host.env from root."
    sudo cp ../control_host.env "$TARGET_ENV"
elif is_valid_env "./control_host.env"; then
    echo "Using local control_host.env."
    sudo cp ./control_host.env "$TARGET_ENV"
else
    echo "Notice: control_host.env not found. Creating template..."
    {
        echo "CONTROL_HOST=192.168.10.252"
        echo "REDIS_PORT=23437"
        echo "REDIS_DB=0"
        echo "OPTUNA_DB_URL=postgresql://postgres:postgres@192.168.10.252:23436/wyoloservice"
    } | sudo tee "$TARGET_ENV" > /dev/null
fi

echo "Copying scripts and configurations to /home/wisrovi/scripts/..."
sudo cp launcher_invoker.sh /home/wisrovi/scripts/launcher_worker.sh
sudo cp docker-compose.yaml /home/wisrovi/scripts/docker-compose.yaml

# Copy system unit file
sudo cp worker_invoker@.service /etc/systemd/system/

# Give execution permissions to the launcher
sudo chmod +x /home/wisrovi/scripts/launcher_worker.sh

# --- 6. SERVICE ACTIVATION ---
sudo systemctl daemon-reload

echo "Enabling service: worker_invoker@$WORKER_IP"
sudo systemctl enable "worker_invoker@$WORKER_IP"
sudo systemctl restart "worker_invoker@$WORKER_IP"

# Try to get the CONTROL_HOST IP for the final summary
CH_IP=$(grep "CONTROL_HOST=" "$TARGET_ENV" | cut -d'=' -f2)

echo "-------------------------------------------------------"
echo "Installation completed successfully!"
echo "Service: worker_invoker@$WORKER_IP"
echo "Working directory: /home/wisrovi/scripts/"
echo "Control Server (IP): ${CH_IP:-Not configured}"
echo "-------------------------------------------------------"
