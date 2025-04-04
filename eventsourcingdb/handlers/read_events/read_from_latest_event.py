from dataclasses import dataclass

from .if_event_is_missing_during_read import IfEventIsMissingDuringRead


@dataclass
class ReadFromLatestEvent:
    subject: str
    type: str
    if_event_is_missing: IfEventIsMissingDuringRead

    def to_json(self):
        return {
            'subject': self.subject,
            'type': self.type,
            'ifEventIsMissing': self.if_event_is_missing
        }
