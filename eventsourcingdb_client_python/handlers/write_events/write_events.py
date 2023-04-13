from ...abstract_base_client import AbstractBaseClient
from ...errors.custom_error import CustomError
from ...errors.internal_error import InternalError
from ...errors.invalid_parameter_error import InvalidParameterError
from ...errors.server_error import ServerError
from ...errors.validation_error import ValidationError
from ...event.event_candidate import EventCandidate
from ...event.event_context import EventContext
from .preconditions import Precondition
from http import HTTPStatus
import json
import requests
from typing import List


def write_events(
		client: AbstractBaseClient,
		event_candidates: List[EventCandidate],
		preconditions: List[Precondition]
) -> List[EventContext]:
	if len(event_candidates) < 1:
		raise InvalidParameterError(
			'event_candidates',
			'event_candidates must contain at least one EventCandidate.'
		)

	for event_candidate in event_candidates:
		try:
			event_candidate.validate()
		except ValidationError as validation_error:
			raise InvalidParameterError('event_candidates', validation_error.message())
		except Exception as other_error:
			raise InternalError(str(other_error))

	request_body = json.dumps({
		'events': [event_candidate.to_json() for event_candidate in event_candidates],
		'preconditions': [precondition.to_json() for precondition in preconditions]
	})

	response: requests.Response
	try:
		response = client.http_client.post(
			path='/api/write-events',
			request_body=request_body
		)
	except CustomError as custom_error:
		raise custom_error
	except Exception as other_error:
		raise InternalError(str(other_error))

	if response.status_code != HTTPStatus.OK:
		raise ServerError(f'Unexpected response status: {response.status_code} {HTTPStatus(response.status_code).phrase}.')

	response_data = response.json()

	if not isinstance(response_data, list):
		raise ServerError(f'Failed to parse response \'{response_data}\' to list.')

	return_value = []
	for unparsed_event_context in response_data:
		try:
			event_context = EventContext.parse(unparsed_event_context)
			return_value.append(event_context)
		except ValidationError as validation_error:
			raise ServerError(validation_error.message())
		except Exception as other_error:
			raise InternalError(str(other_error))

	return return_value

