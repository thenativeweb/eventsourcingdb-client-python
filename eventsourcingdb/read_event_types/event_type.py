from dataclasses import dataclass
from typing import TypeVar, Any

from ..errors import ValidationError

Self = TypeVar("Self", bound="EventType")


@dataclass
class EventType:
    event_type: str
    is_phantom: bool
    schema: dict[str, Any] | None = None

    @staticmethod
    def parse(unknown_object: dict) -> "EventType":
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
        if schema is not None and not isinstance(schema, (dict)):
            raise ValidationError(
                f"Failed to parse schema '{schema}'. Schema must be dict."
            )

        return EventType(
            event_type=event_type,
            is_phantom=is_phantom,
            schema=schema,
        )

    def __hash__(self):
        # Convert dictionary schema to a hashable form (tuple of items)
        if isinstance(self.schema, dict):
            # Sort items to ensure consistent hashing
            schema_items = tuple(sorted((k, str(v)) for k, v in self.schema.items()))
            return hash((self.event_type, self.is_phantom, schema_items))
        return hash((self.event_type, self.is_phantom, self.schema))
