from abc import ABC, abstractmethod
from dataclasses import dataclass


class Precondition(ABC):
	@abstractmethod
	def to_json(self):
		raise NotImplemented


@dataclass
class IsSubjectPristinePrecondition(Precondition):
	subject: str

	def to_json(self):
		return {
			'subject': self.subject
		}


@dataclass
class IsSubjectOnEventIdPrecondition(Precondition):
	subject: str
	event_id: str

	def to_json(self):
		return {
			'subject': self.subject,
			'eventId': self.event_id
		}

