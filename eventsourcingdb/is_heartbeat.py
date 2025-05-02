from typing import Any

HEARTBEAT_TYPE = 'heartbeat'


def is_heartbeat(message: Any) -> bool:
    return isinstance(message, dict) and message.get('type') == HEARTBEAT_TYPE
