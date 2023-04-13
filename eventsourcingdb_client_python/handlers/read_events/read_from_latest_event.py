from dataclasses import dataclass
from enum import Enum


class IfEventIsMissing(Enum):
    READ_NOTHING = 'read-nothing'
    READ_EVERYTHING = 'read-everything'


@dataclass
class ReadFromLatestEvent:
    subject: str
    type: str
    if_event_is_missing: IfEventIsMissing

    def to_json(self):
        return {
            'subject': self.subject,
            'type': self.type,
            'ifEventIsMissing': self.if_event_is_missing
        }
