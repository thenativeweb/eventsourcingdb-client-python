from dataclasses import dataclass

from ...errors.validation_error import ValidationError
from ...event.validate_subject import validate_subject
from ...event.validate_type import validate_type
from ...util.is_non_negativ_integer import is_non_negative_integer
from .read_from_latest_event import ReadFromLatestEvent


@dataclass
class ReadEventsOptions:
    recursive: bool
    chronological: bool | None
    lower_bound_id: str | None
    upper_bound_id: str | None
    from_latest_event: ReadFromLatestEvent | None

    def validate(self) -> None:
        if self.lower_bound_id is not None and not is_non_negative_integer(self.lower_bound_id):
            raise ValidationError(
                'ReadEventOptions are invalid: lower_bound_id must be 0 or greater.'
            )
        if self.upper_bound_id is not None and not is_non_negative_integer(self.upper_bound_id):
            raise ValidationError(
                'ReadEventOptions are invalid: upper_bound_id must be 0 or greater.'
            )

        if self.from_latest_event is not None:
            if self.lower_bound_id is not None:
                raise ValidationError(
                    'ReadEventsOptions are invalid: '
                    'lowerBoundId and fromLatestEvent are mutually exclusive'
                )

            try:
                validate_subject(self.from_latest_event.subject)
            except ValidationError as validation_error:
                raise ValidationError(
                    f'ReadEventsOptions are invalid: '
                    f'Failed to validate \'from_latest_event\': {str(validation_error)}'
                ) from validation_error

            try:
                validate_type(self.from_latest_event.type)
            except ValidationError as validation_error:
                raise ValidationError(
                    f'ReadEventsOptions are invalid: '
                    f'Failed to validate \'from_latest_event\': {str(validation_error)}'
                ) from validation_error

    def to_json(self):
        json = {
            'recursive': self.recursive
        }

        if self.chronological is not None:
            json['chronological'] = self.chronological
        if self.lower_bound_id is not None:
            json['lowerBoundId'] = self.lower_bound_id
        if self.upper_bound_id is not None:
            json['upperBoundId'] = self.upper_bound_id
        if self.from_latest_event is not None:
            json['fromLatestEvent'] = self.from_latest_event.to_json()

        return json
