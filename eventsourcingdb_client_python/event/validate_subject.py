from ..errors.validation_error import ValidationError
import re

word_pattern = '[0-9A-Za-z_-]+'
subject_pattern = f'^/({word_pattern}/)*({word_pattern}/?)?$'


def validate_subject(subject: str) -> None:
    match = re.search(subject_pattern, subject)

    if match is None:
        raise ValidationError(
            f'Failed to validate subject: \'{subject}\' must be an absolute, slash-separated path.'
        )
