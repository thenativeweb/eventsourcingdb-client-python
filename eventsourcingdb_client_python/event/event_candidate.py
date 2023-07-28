from dataclasses import dataclass

from .tracing import TracingContext
from .validate_subject import validate_subject
from .validate_type import validate_type


@dataclass
class EventCandidate:
    source: str
    subject: str
    type: str
    data: dict
    tracing_context: TracingContext | None

    def validate(self) -> None:
        validate_subject(self.subject)
        validate_type(self.type)

    def to_json(self):
        json = {
            'data': self.data,
            'source': self.source,
            'subject': self.subject,
            'type': self.type
        }

        if self.tracing_context is not None:
            json['tracingContext'] = self.tracing_context.to_json()

        return json
