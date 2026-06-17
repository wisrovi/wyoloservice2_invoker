# 🚀 Train Service: Production Invoker

This directory contains the files necessary to deploy a **Worker Invoker** in a Linux production environment (Ubuntu/Debian preferred).

## Content

- `docker-compose.yaml`: Defines services (Worker and Gradio Launcher) using pre-built images from Docker Hub.
- `install.sh`: Automatic installation script that configures directories, generates system metadata, and activates a **Systemd** service.
- `uninstall.sh`: Script to completely clean up the installation.
- `launcher_invoker.sh`: Bridge script between Systemd and Docker Compose.
- `worker_invoker@.service`: Service template for Systemd.
- `Makefile`: Shorthand commands for quick management.

## Quick Installation

1. Ensure you have Docker and Docker Compose installed.
2. Configure the `control_host.env` file with your control server's IP (if it doesn't exist, the installer will create a template).
3. Execute:
   ```bash
   make install
   ```

## Management

- **View status**: `make status`
- **View logs**: `make logs`
- **Uninstall**: `make uninstall`

## Technical Notes

- The worker automatically registers in Celery using its local IP as a unique name.
- The service is configured to restart automatically if it fails.
- Training results are saved in `/home/wyolo/train_service_results`.
