import os
import time
import httpx

url = os.getenv("EVALSCOPE_URL", "http://127.0.0.1:8000")
for attempt in range(60):
    try:
        httpx.get(url + "/health", timeout=1).raise_for_status()
        break
    except httpx.HTTPError:
        if attempt == 59:
            raise SystemExit("API did not become healthy within 30 seconds")
        time.sleep(0.5)
