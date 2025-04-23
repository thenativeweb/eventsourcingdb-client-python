from dataclasses import dataclass
from typing import Any

from ..bound import Bound
from ...errors.validation_error import ValidationError
from ...event.validate_subject import validate_subject
from ...event.validate_type import validate_type
from .observe_from_latest_event import ObserveFromLatestEvent


@dataclass
class ObserveEventsOptions:
    recursive: bool
    lower_bound: Bound | None = None
    from_latest_event: ObserveFromLatestEvent | None = None

    def validate(self) -> None:
        if self.lower_bound is not None and not isinstance(self.lower_bound, Bound):
            raise ValidationError(
                'ObserveEventsOptions are invalid: lower_bound must be a Bound object.'
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

    def to_json(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            'recursive': self.recursive,
        }

        # Directly use the object
        if self.lower_bound is not None:
            result['lowerBound'] = self.lower_bound.to_json()

        if self.from_latest_event is not None:
            result['fromLatestEvent'] = self.from_latest_event.to_json()

        return result
