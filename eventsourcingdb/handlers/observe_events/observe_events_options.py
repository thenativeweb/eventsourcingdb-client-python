from dataclasses import dataclass

from ..lower_bound import LowerBound
from ...errors.validation_error import ValidationError
from ...event.validate_subject import validate_subject
from ...event.validate_type import validate_type
from .observe_from_latest_event import ObserveFromLatestEvent


@dataclass
class ObserveEventsOptions:
    recursive: bool
    lower_bound: LowerBound | None = None
    from_latest_event: ObserveFromLatestEvent | None = None

    def validate(self) -> None:
        if self.lower_bound is not None and not isinstance(self.lower_bound, LowerBound):
            raise ValidationError(
                'ObserveEventsOptions are invalid: lower_bound must be a LowerBound object.'
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

        # Directly use the object
        if self.lower_bound is not None:
            json['lowerBound'] = {
                'id': str(self.lower_bound.id),  # Ensure ID is a string
                'type': self.lower_bound.type
            }

        if self.from_latest_event is not None:
            json['fromLatestEvent'] = self.from_latest_event.to_json()

        return json
