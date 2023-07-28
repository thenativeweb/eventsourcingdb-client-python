from opentelemetry.trace import TraceFlags, TraceState

from eventsourcingdb_client_python.event.tracing import TracingContext


def new_tracing_context(trace_id: str, span_id: str) -> TracingContext:
    return TracingContext(
        trace_id=trace_id,
        span_id=span_id,
        trace_flags=TraceFlags.DEFAULT,
        trace_state=TraceState()
    )
