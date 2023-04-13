from typing import Any


def is_heartbeat(message: Any) -> bool:
    return isinstance(message, dict) and message.get('type') == 'heartbeat'
