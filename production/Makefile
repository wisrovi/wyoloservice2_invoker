# Makefile for Worker Invoker Production
# Author: William Rodriguez - wisrovi

.PHONY: install uninstall status logs help

help:
	@echo "Available commands:"
	@echo "  make install   - Installs the service in the system and starts it"
	@echo "  make uninstall - Stops and removes the service and its files"
	@echo "  make status    - Shows the Systemd service status"
	@echo "  make logs      - Shows logs in real time"

install:
	bash install.sh

uninstall:
	bash uninstall.sh

status:
	systemctl status worker_invoker@$$(hostname -I | awk '{print $$1}')

logs:
	journalctl -u worker_invoker@$$(hostname -I | awk '{print $$1}') -f
