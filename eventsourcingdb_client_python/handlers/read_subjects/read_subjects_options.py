from ...event.validate_subject import validate_subject
from dataclasses import dataclass
from typing import Optional


@dataclass
class ReadSubjectsOptions:
	base_subject: Optional[str] = None

	def validate(self):
		if self.base_subject is not None:
			validate_subject(self.base_subject)

	def to_json(self):
		json = dict()

		if self.base_subject is not None:
			json['baseSubject'] = self.base_subject

		return json
