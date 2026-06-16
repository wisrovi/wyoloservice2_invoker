
import os
from celery import Celery
import time

print("--- [MINIMAL WORKER] STARTING ---")
time.sleep(5) # Give network a moment

redis_url = os.getenv("REDIS_URL")
if not redis_url:
    print("--- [MINIMAL WORKER] ERROR: REDIS_URL environment variable not found!")
else:
    print(f"--- [MINIMAL WORKER] Found REDIS_URL: {redis_url}")

    try:
        app = Celery("minimal_app", broker=redis_url, backend=redis_url)
        print("--- [MINIMAL WORKER] Celery app created successfully.")

        @app.task
        def add(x, y):
            return x + y
        
        print("--- [MINIMAL WORKER] Dummy task defined.")
        print("--- [MINIMAL WORKER] Worker should now try to connect...")

    except Exception as e:
        print(f"--- [MINIMAL WORKER] An error occurred during Celery app creation: {e}")

