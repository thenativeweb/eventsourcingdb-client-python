from typing import Any


def is_subject(message: Any) -> bool:
	if not isinstance(message, dict) or message.get('type') != 'subject':
		return False

	payload = message.get('payload')

	return isinstance(payload, dict) and isinstance(payload.get('subject'), str)
