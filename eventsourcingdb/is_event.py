from typing import Any

EVENT_TYPE = 'event'


def is_event(message: Any) -> bool:
    if isinstance(message, dict) and message.get('type') == EVENT_TYPE:
        payload = message.get('payload')
        return isinstance(payload, dict) and isinstance(payload.get('hash'), str)

    if not isinstance(message, dict):
        return False

    payload = message.get('payload')
    return (
        isinstance(payload, dict)
        and isinstance(payload.get('event'), dict)
        and isinstance(payload.get('hash'), str)
    )
