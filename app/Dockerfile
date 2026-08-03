FROM python:3.10-slim
WORKDIR /app

# Install Docker CLI client and curl
RUN apt-get update && apt-get install -y \
    curl \
    && curl -fsSL https://get.docker.com/ | sh \
    && rm -rf /var/lib/apt/lists/*

# Install OpenCode
RUN curl -fsSL https://opencode.ai/install | bash

# The build context will be the 'invoker' folder
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy all code and configs (celery_config.py, config.yaml, worker_gpu.py, micro_train.sh)
COPY . .

# Install micro_train helper script globally
RUN cp micro_train.sh /usr/local/bin/micro_train && \
    chmod +x /usr/local/bin/micro_train

CMD ["celery", "-A", "worker_gpu", "worker", "-Q", "gpus", "--loglevel=info"]
