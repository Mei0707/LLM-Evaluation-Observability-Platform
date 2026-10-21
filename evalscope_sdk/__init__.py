"""Small opt-in metadata-only client for observing real application requests."""

from contextlib import contextmanager
import logging
import os
import time
import uuid
import httpx


class Client:
    def __init__(
        self,
        url="http://127.0.0.1:8000",
        token=None,
        project_id="00000000-0000-4000-8000-000000000001",
        service="my-ai-app",
    ):
        self.url, self.service = url.rstrip("/"), service
        self.headers = {"X-Project-ID": project_id}
        token = token or os.getenv("EVALSCOPE_API_TOKEN")
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    @contextmanager
    def trace(self, strict=False):
        """Best-effort export; strict=True surfaces export failures for tests."""
        trace = Trace(self)
        try:
            with trace.span("request"):
                yield trace
        finally:
            try:
                response = httpx.post(
                    self.url + "/api/v1/traces",
                    headers=self.headers,
                    json={
                        "trace_id": trace.id,
                        "service": self.service,
                        "spans": trace.spans,
                    },
                    timeout=5,
                )
                response.raise_for_status()
            except httpx.HTTPError:
                if strict:
                    raise
                logging.getLogger("evalscope.sdk").warning(
                    "Trace export failed; application request preserved"
                )


class Trace:
    def __init__(self, client):
        self.id, self.spans, self.stack = uuid.uuid4().hex, [], []

    @contextmanager
    def span(self, name, **attributes):
        if name not in {
            "request",
            "retrieval",
            "prompt",
            "generation",
            "tool",
            "evaluation",
        }:
            raise ValueError("Unsupported span operation")
        if set(attributes) - {
            "model",
            "input_tokens",
            "output_tokens",
            "document_count",
            "error_category",
        }:
            raise ValueError(
                "Only allowlisted metadata is supported; do not send prompts or responses"
            )
        span = {
            "name": name,
            "span_id": uuid.uuid4().hex[:16],
            "parent_span_id": self.stack[-1] if self.stack else None,
            "started_at": time.time(),
            "status": "OK",
            "attributes": attributes,
        }
        self.spans.append(span)
        self.stack.append(span["span_id"])
        try:
            yield span["attributes"]
        except BaseException:
            span["status"] = "ERROR"
            span["attributes"]["error_category"] = "unknown"
            raise
        finally:
            self.stack.pop()
            span["ended_at"] = time.time()
