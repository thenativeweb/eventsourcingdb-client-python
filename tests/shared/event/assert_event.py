from eventsourcingdb_client_python.event.event import Event
from eventsourcingdb_client_python.event.tracing import TracingContext


def assert_event(
        event: Event,
        source: str,
        subject: str,
        type_: str,
        data: dict,
        tracing_context: TracingContext | None
):
    assert event.source == source
    assert event.subject == subject
    assert event.type == type_
    assert event.data == data
    assert event.tracing_context == tracing_context
