from typing import Any


def is_stream_error(message: Any) -> bool:
	if not isinstance(message, dict) or message.get('type') != 'error':
		return False

	payload = message.get('payload')

	return isinstance(payload, dict) and isinstance(payload.get('error'), str)
