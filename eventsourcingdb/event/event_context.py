from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

from ..errors.internal_error import InternalError
from ..errors.validation_error import ValidationError

Self = TypeVar("Self", bound="EventContext")


@dataclass
class EventContext:
    source: str
    subject: str
    type: str
    spec_version: str
    event_id: str
    time: datetime
    data_content_type: str
    predecessor_hash: str
    trace_parent: str | None = None
    trace_state: str | None = None

    @staticmethod
    def parse(unknown_object: dict) -> "EventContext":
        source = unknown_object.get('source')
        if not isinstance(source, str):
            raise ValidationError(
                f'Failed to parse source \'{source}\' to string.')

        subject = unknown_object.get('subject')
        if not isinstance(subject, str):
            raise ValidationError(
                f'Failed to parse subject \'{subject}\' to string.')

        event_type = unknown_object.get('type')
        if not isinstance(event_type, str):
            raise ValidationError(
                f'Failed to parse event_type \'{event_type}\' to string.')

        spec_version = unknown_object.get('specversion')
        if not isinstance(spec_version, str):
            raise ValidationError(
                f'Failed to parse spec_version \'{spec_version}\' to string.')

        event_id = unknown_object.get('id')
        if not isinstance(event_id, str):
            raise ValidationError(
                f'Failed to parse event_id \'{event_id}\' to string.')

        time = unknown_object.get('time')
        if not isinstance(time, str):
            raise ValidationError(
                f'Failed to parse time \'{time}\' to datetime.')

        rest, sub_seconds = time.split('.')
        sub_seconds = f'{sub_seconds[:6]:06}'
        try:
            time = datetime.fromisoformat(f'{rest}.{sub_seconds}')
        except ValueError as value_error:
            raise ValidationError(
                f'Failed to parse time \'{time}\' to datetime.') from value_error
        except Exception as other_error:
            raise InternalError(str(other_error)) from other_error

        data_content_type = unknown_object.get('datacontenttype')
        if not isinstance(data_content_type, str):
            raise ValidationError(
                f'Failed to parse data_content_type \'{data_content_type}\' to string.')

        predecessor_hash = unknown_object.get('predecessorhash')
        if not isinstance(predecessor_hash, str):
            raise ValidationError(
                f'Failed to parse predecessor_hash \'{predecessor_hash}\' to string.')

        trace_parent = unknown_object.get('traceparent')
        if trace_parent is not None and not isinstance(trace_parent, str):
            raise ValidationError(
                f'Failed to parse trace_parent \'{trace_parent}\' to string.')

        trace_state = unknown_object.get('tracestate')
        if trace_state is not None and not isinstance(trace_state, str):
            raise ValidationError(
                f'Failed to parse trace_state \'{trace_state}\' to string.')

        return EventContext(
            source=source,
            subject=subject,
            type=event_type,
            spec_version=spec_version,
            event_id=event_id,
            time=time,
            data_content_type=data_content_type,
            predecessor_hash=predecessor_hash,
            trace_parent=trace_parent,
            trace_state=trace_state,
        )

    def to_json(self) -> dict[Any, Any]:
        json = {
            'specversion': self.spec_version,
            'id': self.event_id,
            'time': self.time.isoformat(sep='T'),
            'source': self.source,
            'subject': self.subject,
            'type': self.type,
            'datacontenttype': self.data_content_type,
            'predecessorhash': self.predecessor_hash
        }

        if self.trace_parent is not None:
            json['traceparent'] = self.trace_parent
        if self.trace_state is not None:
            json['tracestate'] = self.trace_state

        return json
