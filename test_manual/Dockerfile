FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY send_task_docker.py .

CMD ["python", "send_task_docker.py"]
