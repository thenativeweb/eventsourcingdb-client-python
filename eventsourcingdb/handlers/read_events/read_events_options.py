from dataclasses import dataclass

from ..lower_bound import LowerBound
from ..upper_bound import UpperBound
from .order import Order
from ...errors.validation_error import ValidationError
from ...event.validate_subject import validate_subject
from .read_from_latest_event import ReadFromLatestEvent


@dataclass
class ReadEventsOptions:
    recursive: bool
    order: Order | None = None
    lower_bound: LowerBound | None = None
    upper_bound: UpperBound | None = None
    from_latest_event: ReadFromLatestEvent | None = None

    def validate(self) -> None:
        # Update validation logic for new object types
        if self.lower_bound is not None and not isinstance(self.lower_bound, LowerBound):
            raise ValidationError(
                'ReadEventOptions are invalid: lower_bound must be a LowerBound object.'
            )

        if self.upper_bound is not None and not isinstance(self.upper_bound, UpperBound):
            raise ValidationError(
                'ReadEventOptions are invalid: upper_bound must be a UpperBound object.'
            )

        if self.from_latest_event is not None:
            if self.lower_bound is not None:
                raise ValidationError(
                    'ReadEventsOptions are invalid: '
                    'lowerBound and fromLatestEvent are mutually exclusive'
                )

            try:
                validate_subject(self.from_latest_event.subject)
            except ValidationError as validation_error:
                raise ValidationError(
                    f'ReadEventsOptions are invalid: '
                    f'from_latest_event.subject: {str(validation_error)}'
                ) from validation_error

            # Add validation for empty type too
            if not self.from_latest_event.type:
                raise ValidationError(
                    'ReadEventsOptions are invalid: '
                    'from_latest_event.type cannot be empty'
                )

    def to_json(self):
        json = {
            'recursive': self.recursive
        }

        if self.order is not None:
            json['order'] = self.order.value

        # Directly use the objects
        if self.lower_bound is not None:
            json['lowerBound'] = {
                'id': str(self.lower_bound.id),  # Ensure ID is a string
                'type': self.lower_bound.type
            }

        if self.upper_bound is not None:
            json['upperBound'] = {
                'id': str(self.upper_bound.id),  # Ensure ID is a string
                'type': self.upper_bound.type
            }

        if self.from_latest_event is not None:
            json['fromLatestEvent'] = self.from_latest_event.to_json()

        return json
