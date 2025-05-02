from typing import Any

EVENT_TYPE_TYPE = 'eventType'


def is_event_type(message: Any) -> bool:
    if not isinstance(message, dict) or message.get('type') != EVENT_TYPE_TYPE:
        return False

    payload = message.get('payload')

    return isinstance(payload, dict)
