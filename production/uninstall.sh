#!/bin/bash
# Uninstaller for Worker Invoker (Production Version)
# Author: William Rodriguez - wisrovi

echo "-------------------------------------------------------"
echo "  Worker Invoker Uninstallation"
echo "-------------------------------------------------------"

# --- 1. INSTANCE DETECTION ---
WORKER_INSTANCE=$(hostname -I | awk '{print $1}')

if [ -f /etc/default/worker_invoker ]; then
    # shellcheck disable=SC1091
    source /etc/default/worker_invoker
    INSTANCE_NAME=${WORKER_NAME:-$WORKER_INSTANCE}
else
    INSTANCE_NAME=$WORKER_INSTANCE
fi

echo "Stopping and disabling service: worker_invoker@$WORKER_INSTANCE"

# --- 2. STOP SERVICE AND CLEAN CONTAINERS ---
sudo systemctl stop "worker_invoker@$WORKER_INSTANCE" 2>/dev/null
sudo systemctl disable "worker_invoker@$WORKER_INSTANCE" 2>/dev/null

# Clean Docker Compose containers
if [ -d /home/wisrovi/scripts/ ]; then
    echo "Cleaning Docker containers..."
    cd /home/wisrovi/scripts/ || exit
    PROJECT_NAME="invoker_${INSTANCE_NAME//./_}"
    sudo docker-compose -p "$PROJECT_NAME" down --remove-orphans
fi

# --- 3. REMOVAL OF SYSTEM FILES ---
echo "Removing configuration and service files..."

sudo rm -f /etc/systemd/system/worker_invoker@.service
sudo rm -f /etc/default/worker_invoker

# --- 4. WORK DIRECTORY CLEANUP ---
# Only remove the files we placed to avoid deleting other user scripts
echo "Cleaning files in /home/wisrovi/scripts/..."
sudo rm -f /home/wisrovi/scripts/launcher_worker.sh
sudo rm -f /home/wisrovi/scripts/docker-compose.yaml
sudo rm -f /home/wisrovi/scripts/user.env
sudo rm -f /home/wisrovi/scripts/control_host.env

# Try to delete the directory if it's empty
sudo rmdir /home/wisrovi/scripts/ 2>/dev/null

# --- 5. COMPLETION ---
sudo systemctl daemon-reload

echo "-------------------------------------------------------"
echo "Uninstallation completed!"
echo "The service and its configurations have been removed."
echo "-------------------------------------------------------"
