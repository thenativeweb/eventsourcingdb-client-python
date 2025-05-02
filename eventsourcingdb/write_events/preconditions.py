from abc import ABC, abstractmethod
from dataclasses import dataclass


class Precondition(ABC):
    @abstractmethod
    def to_json(self):
        raise NotImplementedError()


@dataclass
class IsSubjectPristine(Precondition):
    subject: str

    def to_json(self):
        return {
            'type': 'isSubjectPristine',
            'payload': {
                'subject': self.subject
            }
        }


@dataclass
class IsSubjectOnEventId(Precondition):
    subject: str
    event_id: str

    def to_json(self):
        return {
            'type': 'isSubjectOnEventId',
            'payload': {
                'subject': self.subject,
                'eventId': self.event_id
            }
        }
