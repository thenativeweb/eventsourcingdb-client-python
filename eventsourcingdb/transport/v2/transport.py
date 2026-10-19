import json
from collections.abc import AsyncGenerator, Callable
from contextlib import aclosing
from http import HTTPStatus
from typing import Any

from ...errors import (
    CustomError,
    DbApiError,
    ErrorCode,
    InternalError,
    ServerError,
    ValidationError,
)
from ...event import Event, EventCandidate
from ...event.find_raw_data import defer_raw_data_of_stream_item
from ...http_client import HttpClient, RequestState, Response
from ...observe_events import ObserveEventsOptions
from ...read_event_types import EventType
from ...read_events import ReadEventsOptions
from ...write_events import Precondition
from ..guard_write import guard_write
from ..statuses_without_v2_api import STATUSES_WITHOUT_V2_API
from ..transport import Transport
from .envelopes import Envelope, read_envelope, read_envelopes, unexpected_envelope

PING_PATH = '/api/v2/system/ping'
VERIFY_PATH = '/api/v2/system/verify-token'
WRITE_EVENTS_PATH = '/api/v2/data/write-events'
REGISTER_EVENT_SCHEMA_PATH = '/api/v2/data/register-event-schema'
READ_EVENT_TYPE_PATH = '/api/v2/data/read-event-type'
READ_EVENTS_PATH = '/api/v2/data/read-events'
OBSERVE_EVENTS_PATH = '/api/v2/data/observe-events'
RUN_EVENTQL_QUERY_PATH = '/api/v2/data/run-eventql-query'
READ_SUBJECTS_PATH = '/api/v2/data/read-subjects'
READ_EVENT_TYPES_PATH = '/api/v2/data/read-event-types'

EVENT_TYPE = 'event'
EVENT_TYPE_TYPE = 'eventType'
SUBJECT_TYPE = 'subject'
ROW_TYPE = 'row'

PING_RECEIVED_TYPE = 'io.eventsourcingdb.api.ping-received'
VERIFIED_TYPE = 'io.eventsourcingdb.api.token-verified'
EVENT_SCHEMA_REGISTERED_TYPE = 'io.eventsourcingdb.api.event-schema-registered'

# The key of an envelope that holds the event, in which the data of the event
# is found exactly as the server sent it.
EVENT_KEY = 'data'


# The statuses with which the v2 API refuses a request before it reads it,
# so that a write is certainly not stored.
REFUSING_STATUSES = {
    HTTPStatus.BAD_REQUEST,
    HTTPStatus.UNAUTHORIZED,
    HTTPStatus.REQUEST_TIMEOUT,
    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
    HTTPStatus.TOO_MANY_REQUESTS,
    HTTPStatus.SERVICE_UNAVAILABLE,
}


def is_refusal(error: DbApiError) -> bool:
    """
    Tells whether the server refused a write before it stored anything, as
    the v2 API does with every error item except store-failed, and with the
    statuses above.
    """
    if error.status == HTTPStatus.OK:
        return error.code != ErrorCode.STORE_FAILED

    return error.status in REFUSING_STATUSES


def is_api_event(envelope: Envelope, event_type: str) -> bool:
    """
    Tells whether the envelope holds an event of the API itself of the given
    type, such as the one the server answers a ping with.
    """
    return (
        envelope.type == EVENT_TYPE
        and isinstance(envelope.data, dict)
        and envelope.data.get('type') == event_type
    )


def parse_event(envelope: Envelope) -> Event:
    if envelope.type != EVENT_TYPE or not isinstance(envelope.data, dict):
        raise unexpected_envelope(envelope)

    return Event._parse_from_server(
        envelope.data, defer_raw_data_of_stream_item(envelope.raw, EVENT_KEY)
    )


def parse_event_type(envelope: Envelope) -> EventType:
    if envelope.type != EVENT_TYPE_TYPE or not isinstance(envelope.data, dict):
        raise unexpected_envelope(envelope)

    try:
        return EventType.parse(envelope.data)
    except ValidationError as validation_error:
        raise ServerError(str(validation_error)) from validation_error
    except Exception as other_error:
        raise InternalError(str(other_error)) from other_error


class V2Transport(Transport):
    """
    Speaks the v2 API, which EventSourcingDB offers since 1.3. Reads use the
    HTTP method QUERY, everything else POST, except for the ping, which uses
    GET. It leaves out every optional field instead of sending null, since the
    v2 API rejects null as well as unknown fields.

    A server that answers a path of the v2 API with 404 or 405 no longer
    offers it, for example because it was rolled back to a version without
    it, so the transport then calls the given function with itself, which
    makes the client forget that the server offers the v2 API. The request
    itself fails as it would otherwise.
    """

    api_version = 'v2'

    def __init__(self, http_client: HttpClient, forget: Callable[[Transport], None]) -> None:
        self.__http_client = http_client
        self.__forget = forget

    async def ping(self) -> None:
        # The ping needs no API token, so it gets none.
        response = await self.__get(PING_PATH, with_authorization=False)
        async with response:
            envelope = await read_envelope(response)

        if not is_api_event(envelope, PING_RECEIVED_TYPE):
            raise unexpected_envelope(envelope)

    async def verify_api_token(self) -> None:
        response = await self.__post(VERIFY_PATH)
        async with response:
            envelope = await read_envelope(response)

        if not is_api_event(envelope, VERIFIED_TYPE):
            raise unexpected_envelope(envelope)

    async def write_events(
        self,
        event_candidates: list[EventCandidate],
        preconditions: list[Precondition],
    ) -> list[Event]:
        request: dict[str, Any] = {
            'events': [event_candidate.to_json() for event_candidate in event_candidates],
        }
        if preconditions:
            request['preconditions'] = [precondition.to_json() for precondition in preconditions]

        return await guard_write(
            lambda request_state: self.__write_events(json.dumps(request), request_state),
            is_refusal,
        )

    async def __write_events(self, request_body: str, request_state: RequestState) -> list[Event]:
        response = await self.__post(WRITE_EVENTS_PATH, request_body, request_state)
        async with response, aclosing(read_envelopes(response)) as envelopes:
            return [parse_event(envelope) async for envelope in envelopes]

    async def register_event_schema(self, event_type: str, json_schema: dict[str, Any]) -> None:
        request = {'type': event_type, 'schema': json_schema}

        await guard_write(
            lambda request_state: self.__register_event_schema(json.dumps(request), request_state),
            is_refusal,
        )

    async def __register_event_schema(
        self, request_body: str, request_state: RequestState
    ) -> None:
        response = await self.__post(REGISTER_EVENT_SCHEMA_PATH, request_body, request_state)
        async with response, aclosing(read_envelopes(response)) as read_envelopes_:
            envelopes = [envelope async for envelope in read_envelopes_]

        if len(envelopes) != 1 or not is_api_event(envelopes[0], EVENT_SCHEMA_REGISTERED_TYPE):
            raise ServerError(
                'Failed to register the event schema, the server answered with '
                f'{[envelope.raw.decode("utf-8").strip() for envelope in envelopes]}.'
            )

    async def read_event_type(self, event_type: str) -> EventType:
        request = {'type': event_type}

        response = await self.__query(READ_EVENT_TYPE_PATH, json.dumps(request))
        async with response:
            envelope = await read_envelope(response)

        return parse_event_type(envelope)

    async def read_events(
        self,
        subject: str,
        options: ReadEventsOptions,
    ) -> AsyncGenerator[Event]:
        request = {'subject': subject, 'options': options.to_json()}

        response = await self.__query(READ_EVENTS_PATH, json.dumps(request))
        async with response, aclosing(read_envelopes(response)) as envelopes:
            async for envelope in envelopes:
                yield parse_event(envelope)

    async def observe_events(
        self,
        subject: str,
        options: ObserveEventsOptions,
    ) -> AsyncGenerator[Event]:
        request = {'subject': subject, 'options': options.to_json()}

        response = await self.__query(OBSERVE_EVENTS_PATH, json.dumps(request))
        async with response, aclosing(read_envelopes(response, ends=False)) as envelopes:
            async for envelope in envelopes:
                yield parse_event(envelope)

    async def run_eventql_query(self, query: str) -> AsyncGenerator[Any]:
        request = {'query': query}

        response = await self.__query(RUN_EVENTQL_QUERY_PATH, json.dumps(request))
        async with response, aclosing(read_envelopes(response)) as envelopes:
            async for envelope in envelopes:
                if (
                    envelope.type != ROW_TYPE
                    or not isinstance(envelope.data, dict)
                    or 'value' not in envelope.data
                ):
                    raise unexpected_envelope(envelope)

                yield envelope.data['value']

    async def read_subjects(self, subject: str, recursive: bool) -> AsyncGenerator[str]:
        request = {'subject': subject, 'options': {'recursive': recursive}}

        response = await self.__query(READ_SUBJECTS_PATH, json.dumps(request))
        async with response, aclosing(read_envelopes(response)) as envelopes:
            async for envelope in envelopes:
                if (
                    envelope.type != SUBJECT_TYPE
                    or not isinstance(envelope.data, dict)
                    or not isinstance(envelope.data.get('subject'), str)
                ):
                    raise unexpected_envelope(envelope)

                yield envelope.data['subject']

    async def read_event_types(self) -> AsyncGenerator[EventType]:
        # Reading event types wraps every error of the request that is not one
        # of the client SDK in an InternalError, as for the v1 API.
        try:
            response = await self.__query(READ_EVENT_TYPES_PATH)
        except CustomError:
            raise
        except Exception as error:
            raise InternalError(str(error)) from error

        async with response, aclosing(read_envelopes(response)) as envelopes:
            async for envelope in envelopes:
                yield parse_event_type(envelope)

    # Every request goes through one of these, so that every answer tells
    # whether the server still offers the v2 API.
    async def __get(self, path: str, *, with_authorization: bool) -> Response:
        response = await self.__http_client.get(path, with_authorization=with_authorization)
        self.__forget_if_without_v2_api(response)
        return response

    async def __post(
        self,
        path: str,
        request_body: str | None = None,
        request_state: RequestState | None = None,
    ) -> Response:
        response = await self.__http_client.post(path, request_body, request_state)
        self.__forget_if_without_v2_api(response)
        return response

    async def __query(self, path: str, request_body: str | None = None) -> Response:
        response = await self.__http_client.query(path, request_body)
        self.__forget_if_without_v2_api(response)
        return response

    def __forget_if_without_v2_api(self, response: Response) -> None:
        # Only the status counts, not the Server header, as for the ping that
        # asks whether the server offers the v2 API, since a proxy that only
        # forwards the v1 API answers on its own. Should the server still
        # offer it, the next request merely finds that out again.
        if response.status in STATUSES_WITHOUT_V2_API:
            self.__forget(self)
