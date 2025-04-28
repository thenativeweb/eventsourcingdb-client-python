from typing import Any

# pylint: disable=R0917
# Reason: This method is expected to have many parameters
# due to its business context. Splitting it into smaller
# methods would increase cognitive load and make the
# code less readable.


def assert_event_equals(
        event: Any,  # Use Any instead of "Event" for type annotation
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
