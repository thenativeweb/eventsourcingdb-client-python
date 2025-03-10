from collections.abc import AsyncGenerator
from http import HTTPStatus

from .event_type import EventType
from .is_event_type import is_event_type
from ..is_stream_error import is_stream_error
from ..parse_raw_message import parse_raw_message
from ...abstract_base_client import AbstractBaseClient
from ...errors.custom_error import CustomError
from ...errors.internal_error import InternalError
from ...errors.server_error import ServerError
from ...errors.validation_error import ValidationError
from ...http_client.response import Response

# pylint: disable=R6007
# Reason: This method explicitly specifies the return type as None
# for better readability. Even though it is not necessary,
# it makes the return type clear without needing to read any
# documentation or code.
async def read_event_types(
    client: AbstractBaseClient,
) -> AsyncGenerator[EventType, None]:
    response: Response
    try:
        response = await client.http_client.post(
            path='/api/read-event-types',
            request_body='',
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

            if is_event_type(message):
                event_type: EventType
                try:
                    event_type = EventType.parse(message['payload'])
                except ValidationError as validation_error:
                    raise ServerError(str(validation_error)) from validation_error
                except Exception as other_error:
                    raise InternalError(str(other_error)) from other_error

                yield event_type
                continue

            raise ServerError(
                f'Failed to read event types, an unexpected stream item was received \'{message}\'.'
            )
