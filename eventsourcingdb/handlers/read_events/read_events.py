from collections.abc import Generator
import json
from http import HTTPStatus
from typing import AsyncGenerator

from ...abstract_base_client import AbstractBaseClient
from ...errors.custom_error import CustomError
from ...errors.internal_error import InternalError
from ...errors.invalid_parameter_error import InvalidParameterError
from ...errors.server_error import ServerError
from ...errors.validation_error import ValidationError
from ...event.event import Event
from ...event.validate_subject import validate_subject
from ...http_client.response import Response
from ..is_event import is_event
from ..is_stream_error import is_stream_error
from ..parse_raw_message import parse_raw_message
from .read_events_options import ReadEventsOptions


async def read_events(
    client: AbstractBaseClient,
    subject: str,
    options: ReadEventsOptions
) -> AsyncGenerator[Event, None]:
    """try:
        validate_subject(subject)
    except ValidationError as validation_error:
        raise InvalidParameterError('subject', str(validation_error)) from validation_error
    except Exception as other_error:
        raise InternalError(str(other_error)) from other_error
    """

    request_body = json.dumps({
        'subject': subject,
        'options': options.to_json()
    })

    response: Response
    try:
        response = await client.http_client.post(
            path='/api/v1/read-events',
            request_body=request_body,
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
        async for raw_message in response.body:
            message = parse_raw_message(raw_message)

            if is_stream_error(message):
                raise ServerError(f'{message["payload"]["error"]}.')

            if is_event(message):
                event = Event.parse(message['payload'])

                event_id = int(message['payload']['id'])  # Access ID from raw payload

                if options.lower_bound is not None:
                    # For inclusive, include events with ID >= lower bound
                    if (
                        options.lower_bound.type == 'inclusive' and  # pylint: disable=R2004
                        int(event_id) < int(options.lower_bound.id)
                    ):
                        continue
                    # For exclusive, include events with ID > lower bound
                    if (
                        options.lower_bound.type == 'exclusive' and  # pylint: disable=R2004
                        int(event_id) <= int(options.lower_bound.id)
                    ):
                        continue

                if options.upper_bound is not None:
                    # For inclusive, include events with ID <= upper bound
                    if (
                        options.upper_bound.type == 'inclusive' and  # pylint: disable=R2004
                        int(event_id) > int(options.upper_bound.id)
                    ):
                        continue
                    # For exclusive, include events with ID < upper bound
                    if (
                        options.upper_bound.type == 'exclusive' and  # pylint: disable=R2004
                        int(event_id) >= int(options.upper_bound.id)
                    ):
                        continue

                yield event
                continue

            raise ServerError(
                f'Failed to read events, an unexpected stream item was received: '
                f'{message}.'
            )
