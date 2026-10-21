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

    def traceparent(self):
        from opentelemetry import trace

        ctx = trace.get_current_span().get_span_context()
        return f"00-{ctx.trace_id:032x}-{ctx.span_id:016x}-01"

    def import_application_spans(self, spans):
        from .schemas import OnlineTraceInput

        if not spans:
            return
        validated = OnlineTraceInput(
            trace_id=self.trace_id, service="application", spans=spans
        )
        parent = trace.get_current_span().get_span_context()
        contexts = {}
        remaining = list(validated.spans)
        while remaining:
            for item in list(remaining):
                if item.parent_span_id and item.parent_span_id not in contexts:
                    continue
                ancestor = contexts.get(item.parent_span_id, parent)
                attributes = item.attributes.model_dump(exclude_none=True)
                remote = tracer.start_span(
                    "application." + item.name,
                    context=trace.set_span_in_context(trace.NonRecordingSpan(ancestor)),
                    start_time=int(item.started_at * 1e9),
                    attributes=attributes,
                )
                if item.status == "ERROR":
                    remote.set_status(
                        Status(
                            StatusCode.ERROR,
                            attributes.get("error_category", "application_error"),
                        )
                    )
                remote.end(end_time=int(item.ended_at * 1e9))
                ctx = remote.get_span_context()
                contexts[item.span_id] = ctx
                self.spans.append(
                    {
                        "name": "application." + item.name,
                        "span_id": f"{ctx.span_id:016x}",
                        "parent_span_id": f"{ancestor.span_id:016x}",
                        "started_at": item.started_at,
                        "ended_at": item.ended_at,
                        "duration_ms": (item.ended_at - item.started_at) * 1000,
                        "status": item.status,
                        "attributes": attributes,
                    }
                )
                remaining.remove(item)

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
                record["attributes"] = dict(span.attributes or {})
                record["ended_at"] = time.time()
                record["duration_ms"] = (record["ended_at"] - started) * 1000
