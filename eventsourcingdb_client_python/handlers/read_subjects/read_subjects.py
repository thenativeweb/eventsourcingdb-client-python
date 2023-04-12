from .read_subjects_options import ReadSubjectsOptions
from ...abstract_base_client import AbstractBaseClient
from ...errors.custom_error import CustomError
from ...errors.internal_error import InternalError
from ...errors.invalid_parameter_error import InvalidParameterError
from ...errors.server_error import ServerError
from ...errors.validation_error import ValidationError
import json
from http import HTTPStatus
import requests


def read_subjects(client: AbstractBaseClient, options: ReadSubjectsOptions) -> str:
	try:
		options.validate()
	except ValidationError as validation_error:
		raise InvalidParameterError('options', validation_error.message())
	except Exception as other_error:
		raise InternalError(str(other_error))

	request_body = json.dumps(options.to_json())

	response: requests.Response
	try:
		response = client.http_client.post(
			path='/api/read-subjects',
			request_body=request_body
		)
	except CustomError as custom_error:
		raise custom_error
	except Exception as other_error:
		raise InternalError(str(other_error))

	if response.status_code != HTTPStatus.OK:
		raise ServerError(
			f'Unexpected response status: {response.status_code} {HTTPStatus(response.status_code).phrase}'
		)

	return response.text

