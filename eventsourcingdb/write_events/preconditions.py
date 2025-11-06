from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class Precondition(ABC):
    @abstractmethod
    def to_json(self) -> Any:
        ...


@dataclass
class IsSubjectPristine(Precondition):
    subject: str

    def to_json(self) -> dict[str, Any]:
        return {"type": "isSubjectPristine", "payload": {"subject": self.subject}}


@dataclass
class IsSubjectPopulated(Precondition):
    subject: str

    def to_json(self) -> dict[str, Any]:
        return {"type": "isSubjectPopulated", "payload": {"subject": self.subject}}


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
class IsEventQlQueryTrue(Precondition):
    query: str

    def to_json(self) -> dict[str, Any]:
        return {
            'type': 'isEventQlQueryTrue',
            'payload': {
                'query': self.query
            }
        }
