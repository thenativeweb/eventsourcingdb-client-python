from eventsourcingdb_client_python.event.event import Event

def assert_event_equals(
        event: Event,
        source: str,
        subject: str,
        type_: str,
        data: dict,
        trace_parent: str | None,
        trace_state: str | None
):
    assert event.source == source
    assert event.subject == subject
    assert event.type == type_
    assert event.data == data
    assert event.trace_parent == trace_parent
    assert event.trace_state == trace_state
