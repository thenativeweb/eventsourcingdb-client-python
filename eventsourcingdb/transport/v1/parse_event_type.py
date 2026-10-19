from ...errors import ValidationError
from ...read_event_types import EventType


def parse_event_type(unknown_object: dict) -> EventType:
    """
    Parses an event type as the v1 API sends it, which names the type
    eventType and tells whether it is a phantom, that is, whether it has no
    events, rather than whether it has events.
    """
    is_phantom = unknown_object.get("isPhantom")
    if not isinstance(is_phantom, bool):
        raise ValidationError(f"Failed to parse isPhantom '{is_phantom}' to bool.")

    return EventType.parse({
        "type": unknown_object.get("eventType"),
        "hasEvents": not is_phantom,
        "schema": unknown_object.get("schema"),
    })
