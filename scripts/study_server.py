"""Run the existing API/worker with a metadata-only provider audit for a study."""

import argparse
import json
import os
from pathlib import Path
import time

import uvicorn

from backend.app import worker, usage
from backend.app.providers import Provider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-log", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8003)
    args = parser.parse_args()
    args.audit_log.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    async def started(request):
        request.extensions["study_started"] = time.monotonic()

    async def captured(response):
        await response.aread()
        elapsed = (
            time.monotonic() - response.request.extensions["study_started"]
        ) * 1000
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        job = usage.current_job.get() or {}
        body = json.loads(response.request.content)
        record = {
            "recorded_at": time.time(),
            "run_id": job.get("run_id"),
            "attempt_id": job.get("attempt_id"),
            "result_id": job.get("result_id"),
            "requested_model": body.get("model"),
            "response_model": payload.get("model"),
            "response_id": payload.get("id"),
            "request_id": response.headers.get("x-request-id"),
            "http_status": response.status_code,
            "http_duration_ms": elapsed,
            "finish_reason": (payload.get("choices") or [{}])[0].get("finish_reason"),
            "usage": payload.get("usage"),
        }
        # Never write request headers, credentials, prompts, or response content.
        with os.fdopen(
            os.open(args.audit_log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a"
        ) as stream:
            stream.write(json.dumps(record) + "\n")

    class AuditedProvider(Provider):
        def __init__(self, *provider_args, **kwargs):
            super().__init__(*provider_args, **kwargs)
            self.client.event_hooks = {"request": [started], "response": [captured]}

    worker.Provider = AuditedProvider
    uvicorn.run(
        "backend.app.api:app", host="127.0.0.1", port=args.port, access_log=False
    )


if __name__ == "__main__":
    main()
