from typing import Any


def is_item(message: Any) -> bool:
    if not isinstance(message, dict) or message.get('type') != 'item':
        return False

    payload = message.get('payload')

    return (
        isinstance(payload, dict)
        and isinstance(payload.get('event'), dict)
        and isinstance(payload.get('hash'), str)
    )
