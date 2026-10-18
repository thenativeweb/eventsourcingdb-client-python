import json
from collections import OrderedDict
from collections.abc import AsyncGenerator
from http import HTTPStatus
from typing import Any

from ...errors import (
    CustomError,
    DbApiError,
    InternalError,
    ServerError,
    ValidationError,
)
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
from ..error_of_answer import error_of_answer
from ..transport import Transport
from .code_of_error import (
    READ_EVENT_TYPE_PATH,
    REGISTER_EVENT_SCHEMA_PATH,
    WRITE_EVENTS_PATH,
    code_of_error,
)
from .is_event import is_event
from .is_event_type import is_event_type
from .is_heartbeat import is_heartbeat
from .is_stream_error import is_stream_error
from .is_subject import is_subject
from .parse_event_type import parse_event_type

PING_PATH = '/api/v1/ping'
VERIFY_API_TOKEN_PATH = '/api/v1/verify-api-token'
READ_EVENTS_PATH = '/api/v1/read-events'
RUN_EVENTQL_QUERY_PATH = '/api/v1/run-eventql-query'
OBSERVE_EVENTS_PATH = '/api/v1/observe-events'
READ_SUBJECTS_PATH = '/api/v1/read-subjects'
READ_EVENT_TYPES_PATH = '/api/v1/read-event-types'


async def ensure_answer_is_ok(response: Response, path: str) -> None:
    """
    Ensures that the answer comes from EventSourcingDB and has status 200, and
    raises the error that the server reports otherwise.
    """
    if not is_valid_server_header(response):
        raise ServerError("Server must be EventSourcingDB")
    if response.status != HTTPStatus.OK:
        raise await error_of_answer(
            response, lambda status, text: code_of_error(path, status, text)
        )


def error_of_stream_item(message: dict) -> DbApiError:
    """
    Turns an error item of a stream into the error that the server reports
    with it, which has no code in the v1 API.
    """
    return DbApiError(status=HTTPStatus.OK, description=message['payload']['error'])


class V1Transport(Transport):
    """Speaks the v1 API, which every EventSourcingDB up to 1.2 offers."""

    def __init__(self, http_client: HttpClient) -> None:
        self.__http_client = http_client

    async def ping(self) -> None:
        specversion_field = "specversion"
        type_field = "type"
        ping_received_type = "io.eventsourcingdb.api.ping-received"

        response = await self.__http_client.get(PING_PATH)
        async with response:
            await ensure_answer_is_ok(response, PING_PATH)
            response_body = bytes.decode(await response.read(), encoding="utf-8")

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
            path=VERIFY_API_TOKEN_PATH,
            request_body=request_body,
        )
        async with response:
            await ensure_answer_is_ok(response, VERIFY_API_TOKEN_PATH)

            response_data = await response.read()
            response_data = bytes.decode(response_data, encoding='utf-8')
            response_json = json.loads(response_data)

            if not isinstance(response_json, dict) or 'type' not in response_json:
                raise ServerError(f'Failed to parse response: {response}')

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
            path=WRITE_EVENTS_PATH,
            request_body=request_body,
        )

        async with response:
            await ensure_answer_is_ok(response, WRITE_EVENTS_PATH)
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
            path=READ_EVENTS_PATH,
            request_body=request_body,
        )

        async with response:
            await ensure_answer_is_ok(response, READ_EVENTS_PATH)
            async for raw_message in response.read_lines():
                message = parse_raw_message(raw_message)

                if is_stream_error(message):
                    raise error_of_stream_item(message)

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
            path=RUN_EVENTQL_QUERY_PATH,
            request_body=request_body,
        )

        async with response:
            await ensure_answer_is_ok(response, RUN_EVENTQL_QUERY_PATH)
            async for raw_message in response.read_lines():
                message = parse_raw_message(raw_message)

                if is_heartbeat(message):
                    continue

                if is_stream_error(message):
                    raise error_of_stream_item(message)

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
            path=OBSERVE_EVENTS_PATH,
            request_body=request_body,
        )

        async with response:
            await ensure_answer_is_ok(response, OBSERVE_EVENTS_PATH)
            async for raw_message in response.read_lines():
                message = parse_raw_message(raw_message)

                if is_heartbeat(message):
                    continue

                if is_stream_error(message):
                    raise error_of_stream_item(message)

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
            path=REGISTER_EVENT_SCHEMA_PATH,
            request_body=request_body,
        )

        async with response:
            await ensure_answer_is_ok(response, REGISTER_EVENT_SCHEMA_PATH)

    async def read_subjects(self, subject: str, recursive: bool) -> AsyncGenerator[str]:
        # The v1 API always reads the subject with all its nested subjects, so
        # reading the subject alone keeps only the subject itself, in the form
        # the server lists it in, without a trailing slash.
        normalized_subject = '/' + subject.strip('/')
        request_body = json.dumps({
            'baseSubject': subject
        })

        response: Response = await self.__http_client.post(
            path=READ_SUBJECTS_PATH,
            request_body=request_body,
        )

        async with response:
            await ensure_answer_is_ok(response, READ_SUBJECTS_PATH)
            async for raw_message in response.read_lines():
                message = parse_raw_message(raw_message)

                if is_stream_error(message):
                    raise error_of_stream_item(message)

                if is_subject(message):
                    read_subject = message['payload']['subject']
                    if recursive or read_subject == normalized_subject:
                        yield read_subject
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
            path=READ_EVENT_TYPE_PATH,
            request_body=request_body,
        )

        async with response:
            await ensure_answer_is_ok(response, READ_EVENT_TYPE_PATH)

            response_data = await response.read()
            response_data = bytes.decode(response_data, encoding='utf-8')

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
                path=READ_EVENT_TYPES_PATH,
                request_body='',
            )
        except CustomError:
            raise
        except Exception as error:
            raise InternalError(str(error)) from error

        async with response:
            await ensure_answer_is_ok(response, READ_EVENT_TYPES_PATH)
            async for raw_message in response.read_lines():
                message = parse_raw_message(raw_message)

                if is_stream_error(message):
                    raise error_of_stream_item(message)

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
