import re

from ..errors.validation_error import ValidationError

WORD_PATTERN = '[0-9A-Za-z_-]+'
SUBJECT_PATTERN = f'^/({WORD_PATTERN}/)*({WORD_PATTERN}/?)?$'


def validate_subject(subject: str) -> None:
    if re.search(SUBJECT_PATTERN, subject) is None:
        raise ValidationError(
            f'Failed to validate subject: \'{subject}\' must be an absolute, slash-separated path.'
        )
