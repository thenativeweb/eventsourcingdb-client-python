from dataclasses import dataclass


@dataclass
class EventCandidate:
    source: str
    subject: str
    type: str
    data: dict
    trace_parent: str | None = None
    trace_state: str | None = None

    def to_json(self):
        json = {
            'data': self.data,
            'source': self.source,
            'subject': self.subject,
            'type': self.type
        }

        if self.trace_parent is not None:
            json['traceparent'] = self.trace_parent
        if self.trace_state is not None:
            json['tracestate'] = self.trace_state

        return json
