from collections.abc import AsyncGenerator
import json
from http import HTTPStatus

from ...abstract_base_client import AbstractBaseClient
from ...errors.custom_error import CustomError
from ...errors.internal_error import InternalError
from ...errors.invalid_parameter_error import InvalidParameterError
from ...errors.server_error import ServerError
from ...errors.validation_error import ValidationError
from ...http_client.response import Response
from ..is_stream_error import is_stream_error
from ..parse_raw_message import parse_raw_message
from .is_subject import is_subject
from ...event.validate_subject import validate_subject

# pylint: disable=R6007
# Reason: This method explicitly specifies the return type as None
# for better readability. Even though it is not necessary,
# it makes the return type clear without needing to read any
# documentation or code.
async def read_subjects(
    client: AbstractBaseClient,
    base_subject: str
) -> AsyncGenerator[str, None, None]:
    try:
        validate_subject(base_subject)
    except ValidationError as validation_error:
        raise InvalidParameterError('base_subject', str(validation_error)) from validation_error
    except Exception as other_error:
        raise InternalError(str(other_error)) from other_error

    request_body = json.dumps({
        'baseSubject': base_subject
    })

    response: Response
    try:
        response = await client.http_client.post(
            path='/api/read-subjects',
            request_body=request_body,
        )
    except CustomError as custom_error:
        raise custom_error
    except Exception as other_error:
        raise InternalError(str(other_error)) from other_error

    with response:
        if response.status_code != HTTPStatus.OK:
            raise ServerError(
                'Unexpected response status: '
                f'{response.status_code} {HTTPStatus(response.status_code).phrase}'
            )
        async for raw_message in response.body:
            message = parse_raw_message(raw_message)

            if is_stream_error(message):
                raise ServerError(message['payload']['error'])

            if is_subject(message):
                yield message['payload']['subject']
                continue

            raise ServerError(
                f'Failed to read subjects, an unexpected stream item was received \'{message}\'.'
            )
