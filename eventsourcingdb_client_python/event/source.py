from dataclasses import dataclass

from eventsourcingdb_client_python.event.event_candidate import EventCandidate


@dataclass
class Source:
    source: str

    def new_event(
        self,
        subject: str,
        event_type: str,
        data: dict
    ) -> EventCandidate:
        return EventCandidate(self.source, subject, event_type, data)
