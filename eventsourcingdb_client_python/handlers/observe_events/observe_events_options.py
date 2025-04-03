from dataclasses import dataclass

from ..lower_bound import LowerBound
from ...errors.validation_error import ValidationError
from .observe_from_latest_event import ObserveFromLatestEvent


@dataclass
class ObserveEventsOptions:
    recursive: bool
    lower_bound: LowerBound | None = None  # Changed from str to LowerBound
    from_latest_event: ObserveFromLatestEvent | None = None

    def validate(self) -> None:
        # Update validation logic
        if self.lower_bound is not None and not isinstance(self.lower_bound, LowerBound):
            raise ValidationError(
                'ObserveEventsOptions are invalid: lower_bound must be a LowerBound object.'
            )
            
        # Rest of validation logic
        # ...

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