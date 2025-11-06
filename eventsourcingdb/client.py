from collections import OrderedDict
from collections.abc import AsyncGenerator

from types import TracebackType
from typing import Any, TypeAlias, TypeVar

from http import HTTPStatus
import json

from .is_heartbeat import is_heartbeat
from .is_stream_error import is_stream_error
from .is_event import is_event
from .is_valid_server_header import is_valid_server_header
from .parse_raw_message import parse_raw_message
from .read_events import ReadEventsOptions

from .errors import CustomError, InternalError, ServerError, ValidationError
from .event import Event, EventCandidate
from .observe_events import ObserveEventsOptions
from .read_event_types import EventType, is_event_type
from .read_subjects import is_subject

from .write_events import Precondition
from .http_client import HttpClient, Response


T = TypeVar('T')

# Type aliases for commonly used types
JsonDict: TypeAlias = dict[str, Any]
EventCandidateList: TypeAlias = list[EventCandidate]
PreconditionList: TypeAlias = list[Precondition]
EventStream: TypeAlias = AsyncGenerator[Event, None]
EventTypeStream: TypeAlias = AsyncGenerator[EventType, None]
SubjectStream: TypeAlias = AsyncGenerator[str, None]


class Client():
    def __init__(
        self,
        base_url: str,
        api_token: str,
    ) -> None:
        self.__http_client = HttpClient(base_url=base_url, api_token=api_token)

    async def __aenter__(self) -> 'Client':
        await self.__http_client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: BaseException | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        await self.__http_client.__aexit__(exc_type, exc_val, exc_tb)

    @property
    def http_client(self) -> HttpClient:
        return self.__http_client

    def _validate_response(self, response: Response, error_message: str | None = None) -> None:
        """Validate that response comes from EventSourcingDB and has OK status."""
        if not is_valid_server_header(response):
            raise ServerError("Server must be EventSourcingDB")
        if response.status_code != HTTPStatus.OK:
            msg = error_message or f"Unexpected response status: {response}"
            raise ServerError(msg)

    async def ping(self) -> None:
        specversion_field = "specversion"
        type_field = "type"
        ping_received_type = "io.eventsourcingdb.api.ping-received"

        response = await self.http_client.get("/api/v1/ping")
        if not is_valid_server_header(response):
            raise ServerError("Server must be EventSourcingDB")
        response_body = bytes.decode(await response.body.read(), encoding="utf-8")

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

        response: Response = await self.http_client.post(
            path='/api/v1/verify-api-token',
            request_body=request_body,
        )
        async with response:
            self._validate_response(response, f"Failed to verify API token: {response}")

            response_data = await response.body.read()
            response_data = bytes.decode(response_data, encoding='utf-8')
            response_json = json.loads(response_data)

            if not isinstance(response_json, dict) or 'type' not in response_json:
                raise ServerError('Failed to parse response: {response}')

            expected_event_type = 'io.eventsourcingdb.api.api-token-verified'
            if response_json.get('type') != expected_event_type:
                raise ServerError(f'Failed to verify API token: {response}')

    async def write_events(
        self,
        event_candidates: EventCandidateList,
        preconditions: PreconditionList | None = None
    ) -> list[Event]:
        if preconditions is None:
            preconditions = []

        request_body = json.dumps(
            {
                'events': [event_candidate.to_json() for event_candidate in event_candidates],
                'preconditions': [precondition.to_json() for precondition in preconditions]
            }
        )

        response = await self.http_client.post(
            path='/api/v1/write-events',
            request_body=request_body,
        )

        self._validate_response(response)

        response_data = await response.body.read()
        response_data = bytes.decode(response_data, encoding='utf-8')
        response_data = json.loads(response_data, object_pairs_hook=OrderedDict)

        if not isinstance(response_data, list):
            raise ServerError(
                f'Failed to parse response \'{response_data}\' to list.')

        result = []
        for unparsed_event_context in response_data:
            result.append(Event.parse(unparsed_event_context))
        return result

    async def read_events(
        self,
        subject: str,
        options: ReadEventsOptions
    ) -> EventStream:
        request_body = json.dumps({
            'subject': subject,
            'options': options.to_json()
        })
        response: Response = await self.__http_client.post(
            path='/api/v1/read-events',
            request_body=request_body,
        )

        async with response:
            self._validate_response(response)
            async for raw_message in response.body:
                message = parse_raw_message(raw_message)

                if is_stream_error(message):
                    raise ServerError(f'{message["payload"]["error"]}.')

                if is_event(message):
                    event = Event.parse(message['payload'])
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
            self._validate_response(response)
            async for raw_message in response.body:
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
        options: ObserveEventsOptions
    ) -> EventStream:
        request_body = json.dumps({
            'subject': subject,
            'options': options.to_json()
        })

        response: Response = await self.http_client.post(
            path='/api/v1/observe-events',
            request_body=request_body,
        )

        async with response:
            self._validate_response(response)
            async for raw_message in response.body:
                message = parse_raw_message(raw_message)

                if is_heartbeat(message):
                    continue

                if is_stream_error(message):
                    raise ServerError(f'{message["payload"]["error"]}.')

                if is_event(message):
                    event = Event.parse(message['payload'])
                    yield event
                    continue

                raise ServerError(
                    f'Failed to read events, an unexpected stream item was received: '
                    f'{message}.'
                )

    async def register_event_schema(self, event_type: str, json_schema: JsonDict) -> None:
        request_body = json.dumps({
            'eventType': event_type,
            'schema': json_schema,
        })

        response: Response = await self.http_client.post(
            path='/api/v1/register-event-schema',
            request_body=request_body,
        )

        async with response:
            if not is_valid_server_header(response):
                raise ServerError("Server must be EventSourcingDB")
            if response.status_code != HTTPStatus.OK:
                error_body = await response.body.read()
                error_text = bytes.decode(error_body, encoding="utf-8")
                raise ServerError(error_text)

    async def read_subjects(
        self,
        base_subject: str
    ) -> SubjectStream:
        request_body = json.dumps({
            'baseSubject': base_subject
        })

        response: Response = await self.http_client.post(
            path='/api/v1/read-subjects',
            request_body=request_body,
        )

        async with response:
            self._validate_response(response)
            async for raw_message in response.body:
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

        response: Response = await self.http_client.post(
            path='/api/v1/read-event-type',
            request_body=request_body,
        )

        async with response:
            if not is_valid_server_header(response):
                raise ServerError("Server must be EventSourcingDB")

            response_data = await response.body.read()
            response_data = bytes.decode(response_data, encoding='utf-8')

            if response.status_code != HTTPStatus.OK:
                raise ServerError(response_data)

            response_json = json.loads(response_data)

            if not isinstance(response_json, dict):
                raise ServerError(
                    f'Failed to parse response \'{response_json}\' to dict.')

            try:
                return EventType.parse(response_json)
            except ValidationError as validation_error:
                raise ServerError(str(validation_error)) from validation_error
            except Exception as other_error:
                raise InternalError(str(other_error)) from other_error


    async def read_event_types(self) -> EventTypeStream:
        try:
            response = await self.http_client.post(
                path='/api/v1/read-event-types',
                request_body='',
            )
        except CustomError:
            raise
        except Exception as error:
            raise InternalError(str(error)) from error

        async with response:
            self._validate_response(response)
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
                    f'Failed to read event types, an unexpected '
                    f'stream item was received \'{message}\'.'
                )
