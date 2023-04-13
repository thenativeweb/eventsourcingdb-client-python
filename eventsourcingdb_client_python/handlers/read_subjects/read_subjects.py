from ...abstract_base_client import AbstractBaseClient
from ...errors.custom_error import CustomError
from ...errors.internal_error import InternalError
from ...errors.invalid_parameter_error import InvalidParameterError
from ...errors.server_error import ServerError
from ...errors.validation_error import ValidationError
from ..is_stream_error import is_stream_error
from .is_subject import is_subject
from .read_subjects_options import ReadSubjectsOptions
import json
from http import HTTPStatus
import requests
from typing import Generator


def read_subjects(client: AbstractBaseClient, options: ReadSubjectsOptions) -> Generator[str, None, None]:
    try:
        options.validate()
    except ValidationError as validation_error:
        raise InvalidParameterError('options', str(validation_error))
    except Exception as other_error:
        raise InternalError(str(other_error))

    request_body = json.dumps(options.to_json())

    response: requests.Response
    try:
        response = client.http_client.post(
            path='/api/read-subjects',
            request_body=request_body,
            stream_response=True
        )
    except CustomError as custom_error:
        raise custom_error
    except Exception as other_error:
        raise InternalError(str(other_error))

    with response:
        if response.status_code != HTTPStatus.OK:
            raise ServerError(
                f'Unexpected response status: {response.status_code} {HTTPStatus(response.status_code).phrase}'
            )

        for message in response.iter_lines():
            try:
                message = message.decode('utf8')
                message = json.loads(message)
            except Exception as error:
                raise ServerError(str(error))

            if is_stream_error(message):
                raise ServerError(message['payload']['error'])

            if is_subject(message):
                yield message['payload']['subject']
                continue

            raise ServerError(
                f'Failed to read subjects, an unexpected stream item was received \'{message}\'.'
            )
