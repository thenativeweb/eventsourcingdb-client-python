from datetime import datetime
from typing import TypeVar

from .tracing import TracingContext
from ..errors.validation_error import ValidationError
from .event_context import EventContext

Self = TypeVar("Self", bound="Event")


class Event(EventContext):
    def __init__(
        self,
        data: dict,
        source: str,
        subject: str,
        event_type: str,
        spec_version: str,
        event_id: str,
        time: datetime,
        data_content_type: str,
        predecessor_hash: str,
        tracing_context: TracingContext = None
    ):
        super().__init__(
            source,
            subject,
            event_type,
            spec_version,
            event_id,
            time,
            data_content_type,
            predecessor_hash,
            tracing_context
        )
        self.data = data

    @staticmethod
    def parse(unknown_object: dict) -> Self:
        event_context = super(Event, Event).parse(unknown_object)
        data = unknown_object.get('data')
        if not isinstance(data, dict):
            raise ValidationError(
                f'Failed to parse data \'{data}\' to object.'
            )

        return Event(
            data,
            event_context.source,
            event_context.subject,
            event_context.type,
            event_context.spec_version,
            event_context.event_id,
            event_context.time,
            event_context.data_content_type,
            event_context.predecessor_hash,
            event_context.tracing_context
        )

    def to_json(self):
        json = super().to_json()
        json['data'] = self.data

        return json
