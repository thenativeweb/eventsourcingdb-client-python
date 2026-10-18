import json
from collections import OrderedDict
from collections.abc import AsyncGenerator
from http import HTTPStatus
from typing import Any

from ...errors import CustomError, InternalError, ServerError, ValidationError
from ...event import Event, EventCandidate
from ...event.find_raw_data import (
    defer_raw_data_of_events,
    defer_raw_data_of_stream_item,
)
from ...http_client import HttpClient, Response
from ...is_valid_server_header import is_valid_server_header
from ...observe_events import ObserveEventsOptions
from ...parse_raw_message import parse_raw_message
from ...read_event_types import EventType
from ...read_events import ReadEventsOptions
from ...write_events import Precondition
from ..transport import Transport
from .is_event import is_event
from .is_event_type import is_event_type
from .is_heartbeat import is_heartbeat
from .is_stream_error import is_stream_error
from .is_subject import is_subject
from .parse_event_type import parse_event_type


def validate_response(response: Response, error_message: str | None = None) -> None:
    """Validate that response comes from EventSourcingDB and has OK status."""
    if not is_valid_server_header(response):
        raise ServerError("Server must be EventSourcingDB")
    if response.status_code != HTTPStatus.OK:
        msg = error_message or f"Unexpected response status: {response}"
        raise ServerError(msg)


class V1Transport(Transport):
    """Speaks the v1 API, which every EventSourcingDB up to 1.2 offers."""

    def __init__(self, http_client: HttpClient) -> None:
        self.__http_client = http_client

    async def ping(self) -> None:
        specversion_field = "specversion"
        type_field = "type"
        ping_received_type = "io.eventsourcingdb.api.ping-received"

        response = await self.__http_client.get("/api/v1/ping")
        if not is_valid_server_header(response):
            raise ServerError("Server must be EventSourcingDB")
        response_body = bytes.decode(await response.read(), encoding="utf-8")

        if response.status_code != HTTPStatus.OK:
            raise ServerError(f"Received unexpected response: {response_body}")

        response_json = json.loads(response_body)
        if (
            isinstance(response_json, dict)
            and specversion_field in response_json
            and type_field in response_json
            and response_json.get(type_field) == ping_received_type
        ):
            return

        raise ServerError(f"Received unexpected response: {response_body}")

    async def verify_api_token(self) -> None:
        request_body = json.dumps({})

        response: Response = await self.__http_client.post(
            path='/api/v1/verify-api-token',
            request_body=request_body,
        )
        async with response:
            validate_response(response, f"Failed to verify API token: {response}")

            response_data = await response.read()
            response_data = bytes.decode(response_data, encoding='utf-8')
            response_json = json.loads(response_data)

            if not isinstance(response_json, dict) or 'type' not in response_json:
                raise ServerError('Failed to parse response: {response}')

            expected_event_type = 'io.eventsourcingdb.api.api-token-verified'
            if response_json.get('type') != expected_event_type:
                raise ServerError(f'Failed to verify API token: {response}')

    async def write_events(
        self,
        event_candidates: list[EventCandidate],
        preconditions: list[Precondition],
    ) -> list[Event]:
        request_body = json.dumps(
            {
                'events': [event_candidate.to_json() for event_candidate in event_candidates],
                'preconditions': [precondition.to_json() for precondition in preconditions]
            }
        )

        response = await self.__http_client.post(
            path='/api/v1/write-events',
            request_body=request_body,
        )

        validate_response(response)

        response_text = bytes.decode(await response.read(), encoding='utf-8')
        response_data = json.loads(response_text, object_pairs_hook=OrderedDict)

        if not isinstance(response_data, list):
            raise ServerError(
                f'Failed to parse response \'{response_data}\' to list.')

        result = []
        for unparsed_event_context, find_data_from_server in zip(
            response_data, defer_raw_data_of_events(response_text, len(response_data)), strict=True
        ):
            result.append(Event._parse_from_server(unparsed_event_context, find_data_from_server))
        return result

    async def read_events(
        self,
        subject: str,
        options: ReadEventsOptions,
    ) -> AsyncGenerator[Event]:
        request_body = json.dumps({
            'subject': subject,
            'options': options.to_json()
        })
        response: Response = await self.__http_client.post(
            path='/api/v1/read-events',
            request_body=request_body,
        )

        async with response:
            validate_response(response)
            async for raw_message in response.read_lines():
                message = parse_raw_message(raw_message)

                if is_stream_error(message):
                    raise ServerError(f'{message["payload"]["error"]}.')

                if is_event(message):
                    event = Event._parse_from_server(
                        message['payload'],
                        defer_raw_data_of_stream_item(raw_message),
                    )
                    yield event
                    continue

                raise ServerError(
                    f'Failed to read events, an unexpected stream item was received: '
                    f'{message}.'
                )

    async def run_eventql_query(self, query: str) -> AsyncGenerator[Any]:
        request_body = json.dumps({
            'query': query,
        })
        response: Response = await self.__http_client.post(
            path='/api/v1/run-eventql-query',
            request_body=request_body,
        )

        async with response:
            validate_response(response)
            async for raw_message in response.read_lines():
                message = parse_raw_message(raw_message)

                if is_heartbeat(message):
                    continue

                if is_stream_error(message):
                    error_message = message.get('payload', {}).get('error', 'Unknown error')
                    raise ServerError(f"{error_message}.")
                if message.get('type') == 'row':
                    payload = message['payload']

                    yield payload
                    continue

                raise ServerError(
                    'Failed to execute EventQL query, an unexpected stream item was received: '
                    f'{message}.'
                )

    async def observe_events(
        self,
        subject: str,
        options: ObserveEventsOptions,
    ) -> AsyncGenerator[Event]:
        request_body = json.dumps({
            'subject': subject,
            'options': options.to_json()
        })

        response: Response = await self.__http_client.post(
            path='/api/v1/observe-events',
            request_body=request_body,
        )

        async with response:
            validate_response(response)
            async for raw_message in response.read_lines():
                message = parse_raw_message(raw_message)

                if is_heartbeat(message):
                    continue

                if is_stream_error(message):
                    raise ServerError(f'{message["payload"]["error"]}.')

                if is_event(message):
                    event = Event._parse_from_server(
                        message['payload'],
                        defer_raw_data_of_stream_item(raw_message),
                    )
                    yield event
                    continue

                raise ServerError(
                    f'Failed to read events, an unexpected stream item was received: '
                    f'{message}.'
                )

    async def register_event_schema(self, event_type: str, json_schema: dict[str, Any]) -> None:
        request_body = json.dumps({
            'eventType': event_type,
            'schema': json_schema,
        })

        response: Response = await self.__http_client.post(
            path='/api/v1/register-event-schema',
            request_body=request_body,
        )

        async with response:
            if not is_valid_server_header(response):
                raise ServerError("Server must be EventSourcingDB")
            if response.status_code != HTTPStatus.OK:
                error_body = await response.read()
                error_text = bytes.decode(error_body, encoding="utf-8")
                raise ServerError(error_text)

    async def read_subjects(self, subject: str) -> AsyncGenerator[str]:
        request_body = json.dumps({
            'baseSubject': subject
        })

        response: Response = await self.__http_client.post(
            path='/api/v1/read-subjects',
            request_body=request_body,
        )

        async with response:
            validate_response(response)
            async for raw_message in response.read_lines():
                message = parse_raw_message(raw_message)

                if is_stream_error(message):
                    raise ServerError(message['payload']['error'])

                if is_subject(message):
                    yield message['payload']['subject']
                    continue

                raise ServerError(
                    f'Failed to read subjects, an unexpected stream item '
                    f'was received \'{message}\'.'
                )

    async def read_event_type(self, event_type: str) -> EventType:
        request_body = json.dumps({
            'eventType': event_type
        })

        response: Response = await self.__http_client.post(
            path='/api/v1/read-event-type',
            request_body=request_body,
        )

        async with response:
            if not is_valid_server_header(response):
                raise ServerError("Server must be EventSourcingDB")

            response_data = await response.read()
            response_data = bytes.decode(response_data, encoding='utf-8')

            if response.status_code != HTTPStatus.OK:
                raise ServerError(response_data)

            response_json = json.loads(response_data)

            if not isinstance(response_json, dict):
                raise ServerError(
                    f'Failed to parse response \'{response_json}\' to dict.')

            try:
                return parse_event_type(response_json)
            except ValidationError as validation_error:
                raise ServerError(str(validation_error)) from validation_error
            except Exception as other_error:
                raise InternalError(str(other_error)) from other_error

    async def read_event_types(self) -> AsyncGenerator[EventType]:
        try:
            response = await self.__http_client.post(
                path='/api/v1/read-event-types',
                request_body='',
            )
        except CustomError:
            raise
        except Exception as error:
            raise InternalError(str(error)) from error

        async with response:
            validate_response(response)
            async for raw_message in response.read_lines():
                message = parse_raw_message(raw_message)

                if is_stream_error(message):
                    raise ServerError(message['payload']['error'])

                if is_event_type(message):
                    event_type: EventType
                    try:
                        event_type = parse_event_type(message['payload'])
                    except ValidationError as validation_error:
                        raise ServerError(str(validation_error)) from validation_error
                    except Exception as other_error:
                        raise InternalError(str(other_error)) from other_error

                    yield event_type
                    continue

                raise ServerError(
                    f'Failed to read event types, an unexpected '
                    f'stream item was received \'{message}\'.'
                )
