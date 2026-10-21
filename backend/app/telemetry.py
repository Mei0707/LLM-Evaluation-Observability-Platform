import os
import time
from contextlib import contextmanager
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode
from prometheus_client import Counter, Histogram, Gauge

provider = TracerProvider(
    resource=Resource.create(
        {"service.name": os.getenv("OTEL_SERVICE_NAME", "evalscope")}
    )
)
if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("evalscope", "0.1.0")
CASE_DURATION = Histogram(
    "evaluation_duration_seconds",
    "Case execution duration",
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 5, 15, 30, 120),
)
LLM_DURATION = Histogram(
    "llm_request_duration_seconds", "Generation duration", ["provider"]
)
WORKER_ACTIVE = Gauge("evaluation_worker_active", "Active tasks in this process")
HTTP_REQUESTS = Counter(
    "evalscope_http_requests_total", "API requests", ["method", "route", "status_class"]
)
HTTP_DURATION = Histogram(
    "evalscope_http_request_duration_seconds", "API latency", ["route"]
)


class Recorder:
    def __init__(self):
        self.spans = []
        self.trace_id = None
        self.root_context = None

    @contextmanager
    def span(self, operation, **attributes):
        # Only callers' bounded metadata is accepted, never prompt/response text.
        started = time.time()
        context = (
            trace.set_span_in_context(trace.NonRecordingSpan(self.root_context))
            if self.root_context
            and not trace.get_current_span().get_span_context().is_valid
            else None
        )
        with tracer.start_as_current_span(
            operation, attributes=attributes, context=context
        ) as span:
            ctx = span.get_span_context()
            self.trace_id = f"{ctx.trace_id:032x}"
            self.root_context = self.root_context or ctx
            parent = span.parent
            record = {
                "name": operation,
                "span_id": f"{ctx.span_id:016x}",
                "parent_span_id": f"{parent.span_id:016x}" if parent else None,
                "started_at": started,
                "status": "OK",
                "attributes": attributes,
            }
            self.spans.append(record)
            try:
                yield span
            except BaseException as exc:
                record["status"] = "ERROR"
                record["error"] = getattr(exc, "category", type(exc).__name__)
                span.set_status(Status(StatusCode.ERROR, record["error"]))
                raise
            finally:
                record["ended_at"] = time.time()
                record["duration_ms"] = (record["ended_at"] - started) * 1000
