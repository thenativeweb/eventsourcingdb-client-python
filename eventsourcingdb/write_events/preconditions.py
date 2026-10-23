from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .precondition_options import PreconditionOptions


class Precondition(ABC):
    @abstractmethod
    def to_json(self) -> Any:
        ...


def with_options(payload: dict[str, Any], options: PreconditionOptions | None) -> dict[str, Any]:
    # Options that were not given are left out rather than sent as null, which
    # the v2 API rejects.
    if options is None:
        return payload

    return {**payload, "options": options.to_json()}


@dataclass
class IsSubjectPristine(Precondition):
    subject: str
    options: PreconditionOptions | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "isSubjectPristine",
            "payload": with_options({"subject": self.subject}, self.options),
        }


@dataclass
class IsSubjectPopulated(Precondition):
    subject: str
    options: PreconditionOptions | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "isSubjectPopulated",
            "payload": with_options({"subject": self.subject}, self.options),
        }


@dataclass
class IsSubjectOnEventId(Precondition):
    subject: str
    event_id: str
    options: PreconditionOptions | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "isSubjectOnEventId",
            "payload": with_options(
                {"subject": self.subject, "eventId": self.event_id}, self.options
            ),
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
