import json
from typing import Any

from .errors.server_error import ServerError


def parse_raw_message(raw_message: bytes) -> Any:
    decoded_message: str
    try:
        decoded_message = raw_message.decode('utf8')
    except Exception as error:
        raise ServerError(str(error)) from error

    try:
        return json.loads(decoded_message)
    except Exception as error:
        raise ServerError(str(error)) from error
