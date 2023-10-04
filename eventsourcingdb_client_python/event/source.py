from dataclasses import dataclass

from ..event.event_candidate import EventCandidate


@dataclass
class Source:
    source: str

    def new_event(
        self,
        subject: str,
        event_type: str,
        data: dict,
        trace_parent: str = None,
        trace_state: str = None
    ) -> EventCandidate:
        return EventCandidate(
            self.source,
            subject,
            event_type,
            data,
            trace_parent,
            trace_state
        )
