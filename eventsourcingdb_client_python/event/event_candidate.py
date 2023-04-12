from .validate_subject import validate_subject
from .validate_type import validate_type
from dataclasses import dataclass


@dataclass
class EventCandidate:
	data: dict
	source: str
	subject: str
	type: str

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
