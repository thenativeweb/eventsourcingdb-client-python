from dataclasses import dataclass
from typing import TypeVar

from opentelemetry.trace import TraceState, TraceFlags, SpanContext, format_trace_id, format_span_id

from ..errors.validation_error import ValidationError

Self = TypeVar("Self", bound="TracingContext")


@dataclass
class TracingContext:
    trace_id: str
    span_id: str
    trace_flags: TraceFlags
    trace_state: TraceState

    @staticmethod
    def from_span_context(span_context: SpanContext) -> Self:
        return TracingContext(
            trace_id=format_trace_id(span_context.trace_id),
            span_id=format_span_id(span_context.span_id),
            trace_flags=span_context.trace_flags,
            trace_state=span_context.trace_state
        )

    def trace_flags_to_string(self) -> str:
        return format(self.trace_flags, "02x")

    def trace_parent(self) -> str:
        return f'00-{self.trace_id}-{self.span_id}-{self.trace_flags_to_string()}'

    def to_opentelemetry_context_carrier(self):
        return {
            'traceparent': self.trace_parent(),
            'tracestate': self.trace_state.to_header()
        }

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
            'traceFlags': self.trace_flags_to_string(),
            'traceState': self.trace_state.to_header()
        }
