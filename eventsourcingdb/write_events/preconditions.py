from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class Precondition(ABC):
    @abstractmethod
    def to_json(self) -> Any:
        raise NotImplementedError


@dataclass
class IsSubjectPristine(Precondition):
    subject: str

    def to_json(self) -> dict[str, Any]:
        return {"type": "isSubjectPristine", "payload": {"subject": self.subject}}


@dataclass
class IsSubjectOnEventId(Precondition):
    subject: str
    event_id: str

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "isSubjectOnEventId",
            "payload": {"subject": self.subject, "eventId": self.event_id},
        }

@dataclass
class IsEventQlTrue(Precondition):
    query: str

    def to_json(self) -> dict[str, Any]:
        return {
            'type': 'isEventQlTrue',
            'payload': {
                'query': self.query
            }
        }
