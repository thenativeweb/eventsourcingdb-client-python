from ..errors.validation_error import ValidationError
import re

type_pattern = r'^[0-9A-Za-z_-]{2,}.(?:[0-9A-Za-z_-]+.)+[0-9A-Za-z_-]+$'


def validate_type(event_type: str) -> None:
    match = re.search(type_pattern, event_type)

    if match is None:
        raise ValidationError(
            f'Failed to validate type: \'{event_type}\' must be a reverse domain name.'
        )
