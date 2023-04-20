from eventsourcingdb_client_python.event.event import Event


def assert_event(event: Event, source: str, subject: str, type_: str, data: dict):
    assert event.source == source
    assert event.subject == subject
    assert event.type == type_
    assert event.data == data
