from dataclasses import dataclass
from typing import TypeVar

from opentelemetry.trace import TraceState, TraceFlags

from ..errors.validation_error import ValidationError

Self = TypeVar("Self", bound="TracingContext")


@dataclass
class TracingContext:
    trace_id: str
    span_id: str
    trace_flags: TraceFlags
    trace_state: TraceState

    @staticmethod
    def parse(unknown_object: dict) -> Self:
        trace_id = unknown_object.get("traceId")
        if not isinstance(trace_id, str):
            raise ValidationError(
                f'Failed to parse trace id \'{trace_id}\' to string.')

        span_id = unknown_object.get("spanId")
        if not isinstance(span_id, str):
            raise ValidationError(
                f'Failed to parse span id \'{span_id}\' to string.')

        raw_trace_flags = unknown_object.get("traceFlags")
        if not isinstance(raw_trace_flags, str):
            raise ValidationError(
                f'Failed to parse trace flags \'{raw_trace_flags}\' to string.')
        if raw_trace_flags == format(TraceFlags.DEFAULT, "02x"):
            trace_flags = TraceFlags.DEFAULT
        elif raw_trace_flags == format(TraceFlags.SAMPLED, "02x"):
            trace_flags = TraceFlags.SAMPLED
        else:
            raise ValidationError(
                'Trace flags must be either None (0) or Sampled (1).')

        raw_trace_state = unknown_object.get("traceState")
        if not isinstance(raw_trace_state, str):
            raise ValidationError(
                f'Failed to parse trace state \'{raw_trace_state}\' to string.')
        trace_state = TraceState.from_header([raw_trace_state])

        return TracingContext(
            trace_id=trace_id,
            span_id=span_id,
            trace_flags=trace_flags,
            trace_state=trace_state
        )

    def to_json(self):
        return {
            'traceId': self.trace_id,
            'spanId': self.span_id,
            'traceFlags': format(self.trace_flags, "02x"),
            'traceState': self.trace_state.to_header()
        }
