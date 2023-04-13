from typing import Any

SUBJECT_TYPE = 'subject'


def is_subject(message: Any) -> bool:
    if not isinstance(message, dict) or message.get('type') != SUBJECT_TYPE:
        return False

    payload = message.get('payload')

    return isinstance(payload, dict) and isinstance(payload.get('subject'), str)
