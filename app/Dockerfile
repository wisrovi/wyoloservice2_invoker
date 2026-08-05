FROM nvidia/cuda:12.4.0-devel-ubuntu22.04

WORKDIR /app

# Install Python 3.10, Docker CLI client, and curl
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3.10-venv \
    python3-pip \
    curl \
    && curl -fsSL https://get.docker.com/ | sh \
    && rm -rf /var/lib/apt/lists/*

# Make python3.10 the default python3
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1 \
    && update-alternatives --install /usr/bin/pip3 pip3 /usr/bin/pip3.10 1

# Install OpenCode
RUN curl -fsSL https://opencode.ai/install | bash

# The build context will be the 'invoker' folder
COPY requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy all code and configs (celery_config.py, config.yaml, worker_gpu.py, micro_train.sh)
COPY . .

# Install micro_train helper script globally
RUN cp micro_train.sh /usr/local/bin/micro_train && \
    chmod +x /usr/local/bin/micro_train

CMD ["celery", "-A", "worker_gpu", "worker", "-Q", "gpus", "--loglevel=info"]
