from ...event.validate_subject import validate_subject
from typing import Optional


class ReadSubjectsOptions:
	def __init__(self, base_subject: Optional[str] = None):
		self.base_subject = base_subject

	def validate(self):
		if self.base_subject is not None:
			validate_subject(self.base_subject)

	def to_json(self):
		json = dict()

		if self.base_subject is not None:
			json['baseSubject'] = self.base_subject

		return json
