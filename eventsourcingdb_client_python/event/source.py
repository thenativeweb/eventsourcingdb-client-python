from dataclasses import dataclass

from eventsourcingdb_client_python.event.event_candidate import EventCandidate
from eventsourcingdb_client_python.event.tracing import TracingContext


@dataclass
class Source:
    source: str

    def new_event(
        self,
        subject: str,
        event_type: str,
        data: dict,
        tracing_context: TracingContext | None
    ) -> EventCandidate:
        return EventCandidate(self.source, subject, event_type, data, tracing_context)
