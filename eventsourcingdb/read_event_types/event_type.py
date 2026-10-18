from dataclasses import dataclass
from typing import Any

from ..errors import ValidationError


@dataclass
class EventType:
    type: str
    has_events: bool
    schema: dict[str, Any] | None = None

    @staticmethod
    def parse(unknown_object: dict) -> "EventType":
        event_type = unknown_object.get("type")
        if not isinstance(event_type, str):
            raise ValidationError(f"Failed to parse type '{event_type}' to str.")

        has_events = unknown_object.get("hasEvents")
        if not isinstance(has_events, bool):
            raise ValidationError(f"Failed to parse hasEvents '{has_events}' to bool.")

        schema = unknown_object.get("schema")
        if schema is not None and not isinstance(schema, (dict)):
            raise ValidationError(f"Failed to parse schema '{schema}'. Schema must be dict.")

        return EventType(
            type=event_type,
            has_events=has_events,
            schema=schema,
        )

    def __hash__(self) -> int:
        if isinstance(self.schema, dict):
            schema_items = tuple(sorted((k, str(v)) for k, v in self.schema.items()))
            return hash((self.type, self.has_events, schema_items))
        return hash((self.type, self.has_events, self.schema))
