from collections.abc import Generator
import json
from http import HTTPStatus

import requests

from ...client import Client
from ...errors.custom_error import CustomError
from ...errors.internal_error import InternalError
from ...errors.invalid_parameter_error import InvalidParameterError
from ...errors.server_error import ServerError
from ...errors.validation_error import ValidationError
from ...event.event import Event
from ...event.validate_subject import validate_subject
from ..is_heartbeat import is_heartbeat
from ..is_item import is_item
from ..is_stream_error import is_stream_error
from ..parse_raw_message import parse_raw_message
from ..store_item import StoreItem
from .read_events_options import ReadEventsOptions


def read_events(
    client: Client,
    subject: str,
    options: ReadEventsOptions
) -> Generator[StoreItem, None, None]:
    try:
        validate_subject(subject)
    except ValidationError as validation_error:
        raise InvalidParameterError('subject', str(validation_error)) from validation_error
    except Exception as other_error:
        raise InternalError(str(other_error)) from other_error

    try:
        options.validate()
    except ValidationError as validation_error:
        raise InvalidParameterError('options', str(validation_error)) from validation_error
    except Exception as other_error:
        raise InternalError(str(other_error)) from other_error

    request_body = json.dumps({
        'subject': subject,
        'options': options.to_json()
    })

    response: requests.Response
    try:
        response = client.http_client.post(
            path='/api/read-events',
            request_body=request_body,
            stream_response=True
        )
    except CustomError as custom_error:
        raise custom_error
    except Exception as other_error:
        raise InternalError(str(other_error)) from other_error

    with response:
        if response.status_code != HTTPStatus.OK:
            raise ServerError(
                f'Unexpected response status: '
                f'{response.status_code} {HTTPStatus(response.status_code).phrase}'
            )
        for raw_message in response.iter_lines():
            message = parse_raw_message(raw_message)

            if is_heartbeat(message):
                continue

            if is_stream_error(message):
                raise ServerError(f'{message["payload"]["error"]}.')

            if is_item(message):
                event = Event.parse(message['payload']['event'])

                yield StoreItem(event, message['payload']['hash'])
                continue

            raise ServerError(
                f'Failed to read events, an unexpected stream item was received: '
                f'{message}.'
            )
