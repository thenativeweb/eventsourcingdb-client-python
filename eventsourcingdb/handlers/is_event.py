from typing import Any

EVENT_TYPE = 'event'


def is_event(message: Any) -> bool:
    # Check if this is the new format message
    if isinstance(message, dict) and message.get('type') == EVENT_TYPE:
        payload = message.get('payload')
        return isinstance(payload, dict) and isinstance(payload.get('hash'), str)

    # TODO: no backward compatibility for the old format
    # Otherwise check for old format (just for backward compatibility)
    if not isinstance(message, dict):
        return False

    payload = message.get('payload')
    # TODO: no backward compatbility for the old format
    return (
        isinstance(payload, dict)
        and isinstance(payload.get('event'), dict)
        and isinstance(payload.get('hash'), str)
    )
