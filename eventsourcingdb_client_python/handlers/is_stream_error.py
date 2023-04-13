from typing import Any

ERROR_TYPE = 'error'


def is_stream_error(message: Any) -> bool:
    if not isinstance(message, dict) or message.get('type') != ERROR_TYPE:
        return False

    payload = message.get('payload')

    return isinstance(payload, dict) and isinstance(payload.get('error'), str)
