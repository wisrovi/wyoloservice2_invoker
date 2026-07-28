
create_network:
	docker network create train_service


user.env:
	echo "USER=$$(whoami)" > user.env
	echo "TZ=Europe/Madrid" >> user.env
	echo "WORKER_HOST=$$(hostname -I | awk '{print $$1}')" >> user.env
	echo "WORKER_HOSTNAME=$$(hostname)" >> user.env
	echo "WORKER_OS=$$(uname -s)" >> user.env
	echo "WORKER_NAME=$$(uname -s)" >> user.env
	echo "WORKER_KERNEL_VERSION=$$(uname -r)" >> user.env
	echo "WORKER_CPU_CORES=$$(nproc)" >> user.env
	echo "WORKER_GATEWAY=$$(ip route | grep default | awk '{print $$3}')" >> user.env
	echo "WORKER_NETWORK_INTERFACE=$$(ip route | grep default | awk '{print $$5}')" >> user.env
	echo "WORKER_DOCKER_VERSION=$$(docker --version | awk '{print $$3}' | sed 's/,//')" >> user.env
	echo "WORKER_APP_BASE_PATH=$$(pwd)" >> user.env
	echo "WORKER_APP_ENV=production" >> user.env
	echo "WORKER_HOME_DIR=$$HOME" >> user.env
	echo "WORKER_CURRENT_DATE=$$(date '+%Y-%m-%d')" >> user.env
	echo "WORKER_CURRENT_TIME=$$(date '+%H:%M:%S')" >> user.env
	echo "WORKER_GPU_COUNT=$$(nvidia-smi --query-gpu=count --format=csv,noheader)" >> user.env
	echo "WORKER_GPU_MODEL=$$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1)" >> user.env
	echo "WORKER_GPU_MEMORY=$$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -n 1)" >> user.env
	echo "WORKER_GPU_MEMORY=$$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -n 1)" >> user.env
	MEM_TOTAL=$$(awk '/^MemTotal:/ {print $$2}' /proc/meminfo); \
    echo "WORKER_RAM_MEMORY=$$((MEM_TOTAL / 1048576 * 8 / 10))g" >> user.env
	echo "WORKER_CPU_CORES=$$((`nproc` - 1)).0" >> user.env
	echo "PRIVATE_QUEUE=$$(hostname -I | awk '{print $$1}')" >> user.env


config.py:
	python3 -m pip install customtkinter
	python3 production/config.py


start: user.env config.py
	cp user.env ./config/
	[ -f "control_host.env" ] && cp control_host.env ./config/ || true
	docker-compose -f docker-compose.yaml --env-file ./config/user.env  --env-file ./config/control_host.env  --compatibility up -d --build --force-recreate --no-deps  --pull always

build:
	docker-compose -f docker-compose.yaml --env-file ./config/user.env  --env-file ./config/control_host.env  --compatibility up -d --build --force-recreate --no-deps  --pull always

stop:
	docker-compose -f docker-compose.yaml --env-file ./config/user.env  --env-file ./config/control_host.env  down  --remove-orphans

stop-all: stop
	@echo "Force stopping and removing any other wyolo containers (executors/production nodes)..."
	@docker ps -a --filter "name=wyolo_" --format "{{.ID}}" | xargs -r docker rm -f


start_gradio:
	docker-compose -f docker-compose.yaml --env-file ./config/user.env  --env-file ./config/control_host.env  --compatibility up -d --build --force-recreate --no-deps  --pull always gradio_launcher


publish: stop build start stop
	docker push wisrovi/train_service:worker_invoker_v1.0.0

pause-public-queues:
	@sh scripts/pause_public_queues.sh

resume-public-queues:
	@sh scripts/resume_public_queues.sh
