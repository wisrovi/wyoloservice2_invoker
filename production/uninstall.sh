#!/bin/bash
# Uninstaller for Worker Invoker (Production Version)
# Author: William Rodríguez - wisrovi

echo "-------------------------------------------------------"
echo "  Desinstalación de Worker Invoker"
echo "-------------------------------------------------------"

# --- 1. DETECCIÓN DE INSTANCIA ---
WORKER_INSTANCE=$(hostname -I | awk '{print $1}')

if [ -f /etc/default/worker_invoker ]; then
    source /etc/default/worker_invoker
    INSTANCE_NAME=${WORKER_NAME:-$WORKER_INSTANCE}
else
    INSTANCE_NAME=$WORKER_INSTANCE
fi

echo "Deteniendo y deshabilitando servicio: worker_invoker@$WORKER_INSTANCE"

# --- 2. DETENER SERVICIO Y LIMPIAR CONTENEDORES ---
sudo systemctl stop "worker_invoker@$WORKER_INSTANCE" 2>/dev/null
sudo systemctl disable "worker_invoker@$WORKER_INSTANCE" 2>/dev/null

# Limpiar contenedores de Docker Compose
if [ -d /home/wisrovi/scripts/ ]; then
    echo "Limpiando contenedores de Docker..."
    cd /home/wisrovi/scripts/
    PROJECT_NAME="invoker_${INSTANCE_NAME//./_}"
    sudo docker-compose -p "$PROJECT_NAME" down --remove-orphans
fi

# --- 3. ELIMINACIÓN DE ARCHIVOS DE SISTEMA ---
echo "Eliminando archivos de configuración y servicio..."

sudo rm -f /etc/systemd/system/worker_invoker@.service
sudo rm -f /etc/default/worker_invoker

# --- 4. LIMPIEZA DE DIRECTORIOS DE TRABAJO ---
# Solo eliminamos los archivos que nosotros pusimos para no borrar otros scripts del usuario
echo "Limpiando archivos en /home/wisrovi/scripts/..."
sudo rm -f /home/wisrovi/scripts/launcher_worker.sh
sudo rm -f /home/wisrovi/scripts/docker-compose.yaml
sudo rm -f /home/wisrovi/scripts/user.env
sudo rm -f /home/wisrovi/scripts/control_host.env

# Intentar borrar el directorio si está vacío
sudo rmdir /home/wisrovi/scripts/ 2>/dev/null

# --- 5. FINALIZACIÓN ---
sudo systemctl daemon-reload

echo "-------------------------------------------------------"
echo "¡Desinstalación completada!"
echo "El servicio y sus configuraciones han sido eliminados."
echo "-------------------------------------------------------"
