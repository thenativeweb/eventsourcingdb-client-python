import re

from ..errors.validation_error import ValidationError

TYPE_PATTERN = r'^[0-9A-Za-z_-]{2,}\.(?:[0-9A-Za-z_-]+\.)+[0-9A-Za-z_-]+$'


def validate_type(event_type: str) -> None:
    if re.search(TYPE_PATTERN, event_type) is None:
        raise ValidationError(
            f'Failed to validate type: \'{event_type}\' must be a reverse domain name.'
        )
