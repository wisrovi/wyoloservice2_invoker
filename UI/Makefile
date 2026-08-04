# Makefile for WDarwin Ops Unified UI (Gradio Launcher)
# Author: William Rodriguez - wisrovi

.PHONY: build start stop restart logs status clean

# Default target
all: build start

build:
	docker-compose build --no-cache

start:
	docker-compose --env-file ../config/user.env  --env-file ../config/control_host.env up -d

stop:
	docker-compose down

restart:
	docker-compose restart

logs:
	docker-compose logs -f

status:
	docker-compose ps

clean:
	docker-compose down --rmi local --volumes
