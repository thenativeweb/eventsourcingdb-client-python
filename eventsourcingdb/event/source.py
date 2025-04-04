from dataclasses import dataclass

from ..event.event_candidate import EventCandidate


# pylint: disable=R0917
# Reason: This class is expected to have many parameters
# due to its business context. Splitting it into smaller
# methods would increase cognitive load and make the
# code less readable.
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
