from dataclasses import dataclass

from ...errors.validation_error import ValidationError
from ...event.validate_subject import validate_subject
from ...event.validate_type import validate_type
from ...util.is_non_negativ_integer import is_non_negative_integer
from .observe_from_latest_event import ObserveFromLatestEvent


@dataclass
class ObserveEventsOptions:
    recursive: bool
    lower_bound: str | None = None
    from_latest_event: ObserveFromLatestEvent | None = None

    def validate(self) -> None:
        if self.lower_bound is not None and not is_non_negative_integer(self.lower_bound):
            raise ValidationError(
                'ReadEventOptions are invalid: lower_bound must be 0 or greater.'
            )

        if self.from_latest_event is not None:
            if self.lower_bound is not None:
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

        if self.lower_bound is not None:
            json['lowerBoundId'] = self.lower_bound
        if self.from_latest_event is not None:
            json['fromLatestEvent'] = self.from_latest_event.to_json()

        return json
