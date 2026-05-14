#!/bin/bash
# Installer for Worker Invoker
# Author: William Rodríguez - wisrovi

# --- 1. DETECCIÓN Y PETICIÓN DE DATOS ---
IP_SUGERIDA=$(hostname -I | awk '{print $1}')

echo "-------------------------------------------------------"
echo "  Configuración de Worker Invoker para Train Service"
echo "-------------------------------------------------------"

# Petición profesional con valor por defecto
read -p "Introduzca la IP o Hostname de REDIS [$IP_SUGERIDA:23437]: " REDIS_INPUT
REDIS_HOST=${REDIS_INPUT:-$IP_SUGERIDA}:23437

echo "Configurando Redis en: $REDIS_HOST"

# --- 2. PREPARACIÓN DE ARCHIVOS ---
sudo mkdir -p /home/wisrovi/scripts/
sudo mkdir -p /etc/default/

# Crear el archivo de environment dinámicamente
echo "REDIS_HOST=$REDIS_HOST" | sudo tee /etc/default/worker_invoker > /dev/null
echo "WORKER_NAME=$(hostname -I | awk '{print $1}')" | sudo tee -a /etc/default/worker_invoker > /dev/null

# Copiar archivos de sistema
sudo cp launcher_invoker.sh /home/wisrovi/scripts/launcher_worker.sh
sudo cp worker_invoker@.service /etc/systemd/system/

# --- 3. DESPLIEGUE ---
sudo systemctl daemon-reload

# Habilitar e iniciar usando el hostname local como nombre de instancia
# Esto separa el NOMBRE del worker (instancia) de la IP de REDIS (config)
WORKER_INSTANCE=$(hostname -I | awk '{print $1}')
sudo systemctl enable "worker_invoker@${WORKER_INSTANCE}"
sudo systemctl start "worker_invoker@${WORKER_INSTANCE}"

echo "-------------------------------------------------------"
echo "¡Instalación completada con éxito!"
echo "Servicio: worker_invoker@${WORKER_INSTANCE}"
echo "Redis: $REDIS_HOST"
echo "-------------------------------------------------------"