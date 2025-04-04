from dataclasses import dataclass
from typing import TypeVar

from ...errors.validation_error import ValidationError

Self = TypeVar("Self", bound="EventType")


@dataclass
class EventType:
    event_type: str
    is_phantom: bool
    schema: str | None = None

    @staticmethod
    def parse(unknown_object: dict) -> Self:
        event_type = unknown_object.get('eventType')
        if not isinstance(event_type, str):
            raise ValidationError(
                f"Failed to parse eventType '{event_type}' to str."
            )

        is_phantom = unknown_object.get('isPhantom')
        if not isinstance(is_phantom, bool):
            raise ValidationError(
                f"Failed to parse isPhantom '{is_phantom}' to bool."
            )

        schema = unknown_object.get('schema')
        if schema is not None and not isinstance(schema, str):
            raise ValidationError(
                f"Failed to parse schema '{schema}' to str."
            )

        return EventType(
            event_type=event_type,
            is_phantom=is_phantom,
            schema=schema,
        )

    def __hash__(self):
        return hash((self.event_type, self.is_phantom, self.schema))
