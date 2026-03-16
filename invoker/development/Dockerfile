FROM python:3.10-slim
WORKDIR /app

# The build context will be the 'invoker' folder
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy all code and configs (celery_config.py, config.yaml, worker_gpu.py)
COPY . .

CMD ["celery", "-A", "worker_gpu", "worker", "-Q", "gpus", "--loglevel=info"]
