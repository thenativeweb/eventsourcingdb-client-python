from dataclasses import dataclass

from .validate_subject import validate_subject
from .validate_type import validate_type


@dataclass
class EventCandidate:
    source: str
    subject: str
    type: str
    data: dict

    def validate(self) -> None:
        validate_subject(self.subject)
        validate_type(self.type)

    def to_json(self):
        return {
            'data': self.data,
            'source': self.subject,
            'subject': self.subject,
            'type': self.type
        }
