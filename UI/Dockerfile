FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY gradio_launcher/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY gradio_launcher/ .

# Expose Gradio port
EXPOSE 7860

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV GRADIO_SERVER_NAME="0.0.0.0"

CMD ["python", "gradio_app.py"]
