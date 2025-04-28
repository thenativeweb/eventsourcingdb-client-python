import json
from collections.abc import AsyncGenerator
from http import HTTPStatus

from eventsourcingdb.abstract_base_client import AbstractBaseClient

from ..is_heartbeat import is_heartbeat
from ..is_event import is_event
from ..is_stream_error import is_stream_error
from ..parse_raw_message import parse_raw_message
from ...errors.custom_error import CustomError
from ...errors.internal_error import InternalError
from ...errors.server_error import ServerError
from ...event.event import Event
from .observe_events_options import ObserveEventsOptions
from ...http_client.response import Response


async def observe_events(
    client: AbstractBaseClient,
    subject: str,
    options: ObserveEventsOptions
) -> AsyncGenerator[Event]:
    request_body = json.dumps({
        'subject': subject,
        'options': options.to_json()
    })

    response: Response
    try:
        response = await client.http_client.post(
            path='/api/v1/observe-events',
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

            if is_heartbeat(message):
                continue

            if is_stream_error(message):
                raise ServerError(f'{message["payload"]["error"]}.')

            if is_event(message):
                event = Event.parse(message['payload'])
                event_id = int(message['payload']['id'])

                if options.lower_bound is not None:
                    if (
                        options.lower_bound.type == 'inclusive' and  # pylint: disable=R2004
                        int(event_id) < int(options.lower_bound.id)
                    ):
                        continue
                    if (
                        options.lower_bound.type == 'exclusive' and  # pylint: disable=R2004
                        int(event_id) <= int(options.lower_bound.id)
                    ):
                        continue

                yield event
                continue

            raise ServerError(
                f'Failed to read events, an unexpected stream item was received: '
                f'{message}.'
            )
