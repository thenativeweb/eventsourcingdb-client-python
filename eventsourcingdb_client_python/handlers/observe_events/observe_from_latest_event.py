from dataclasses import dataclass

from ..if_event_is_missing import IfEventIsMissing


@dataclass
class ObserveFromLatestEvent:
    subject: str
    type: str
    if_event_is_missing: IfEventIsMissing

    def to_json(self):
        return {
            'subject': self.subject,
            'type': self.type,
            'ifEventIsMissing': self.if_event_is_missing
        }
