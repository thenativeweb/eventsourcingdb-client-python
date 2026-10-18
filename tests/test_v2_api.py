import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from aiohttp import web

from eventsourcingdb import (
    Bound,
    BoundType,
    Client,
    CustomError,
    DbApiError,
    ErrorCode,
    EventCandidate,
    EventType,
    IfEventIsMissingDuringObserve,
    IfEventIsMissingDuringRead,
    IsSubjectOnEventId,
    ObserveEventsOptions,
    ObserveFromLatestEvent,
    Order,
    OutcomeUnknownError,
    ReadEventsOptions,
    ReadFromLatestEvent,
    ReadSubjectsOptions,
    ServerError,
)

from .event.fixtures import READ_EVENTS_FROM_V2_API, WRITTEN_EVENTS_FROM_V2_API
from .shared.requests import (
    ALL_REQUESTS,
    STREAMS,
    WRITES,
    Request,
    observe_events,
    read_event_type,
    read_event_types,
    read_events,
    read_subjects,
    run_eventql_query,
)

# The ping of the v2 API is the ping that the client asks with whether the
# server offers the v2 API, which the stream server answers on its own.
REQUESTS_EXCEPT_PING = [parameter for parameter in ALL_REQUESTS if parameter.id != 'ping']
from .shared.stream_server import StreamServer

GUARD_TIMEOUT_SECONDS = 5

END = '{"type":"end","data":{}}'
HEARTBEAT = '{"type":"heartbeat","data":{}}'
TOKEN_VERIFIED = '{"type":"event","data":{"type":"io.eventsourcingdb.api.token-verified"}}'
EVENT_SCHEMA_REGISTERED = (
    '{"type":"event","data":{"type":"io.eventsourcingdb.api.event-schema-registered"}}'
)
EVENT_TYPE = (
    '{"type":"eventType","data":'
    '{"type":"io.eventsourcingdb.library.book-acquired","hasEvents":true,"schema":null}}'
)
EVENT_TYPE_WITH_SCHEMA = (
    '{"type":"eventType","data":'
    '{"type":"io.eventsourcingdb.library.book-lent","hasEvents":false,"schema":{"type":"object"}}}'
)
ERROR = json.dumps({
    'type': 'error',
    'data': {
        'code': 'https://docs.eventsourcingdb.io/errors/precondition-violated',
        'description': '/preconditions/0: precondition isSubjectPristine does not hold',
        'details': {'precondition': 0},
    },
})


def answer_with_lines(*lines: str, then_stall: bool = False) -> Callable[[web.StreamResponse], Awaitable[None]]:
    async def write_stream(response: web.StreamResponse) -> None:
        for line in lines:
            await response.write(line.encode('utf-8') + b'\n')
        if then_stall:
            await asyncio.Event().wait()

    return write_stream


def contains_null(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, dict):
        return any(contains_null(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_null(item) for item in value)
    return False


class TestCallsOfTheV2Api:
    @staticmethod
    @pytest.mark.asyncio
    async def test_pings_with_get() -> None:
        async with StreamServer(None, api='v2') as server:
            await server.get_client().ping()

            # The ping of the v2 API is the one that the client asks with
            # whether the server offers the v2 API.
            assert server.probe_count == 2
            assert server.requests == []

    @staticmethod
    @pytest.mark.asyncio
    async def test_verifies_the_token_with_post_and_no_body() -> None:
        async with StreamServer(answer_with_lines(TOKEN_VERIFIED), api='v2') as server:
            await server.get_client().verify_api_token()

            [request] = server.requests
            assert (request.method, request.path, request.body) == (
                'POST',
                '/api/v2/system/verify-token',
                b'',
            )

    @staticmethod
    @pytest.mark.asyncio
    async def test_fails_to_verify_the_token_if_the_server_answers_with_another_event() -> None:
        async with StreamServer(answer_with_lines(EVENT_SCHEMA_REGISTERED), api='v2') as server:
            with pytest.raises(ServerError, match='unexpected item'):
                await server.get_client().verify_api_token()

    @staticmethod
    @pytest.mark.asyncio
    async def test_writes_events_with_post_and_returns_them_as_stored() -> None:
        async with StreamServer(
            answer_with_lines(HEARTBEAT, WRITTEN_EVENTS_FROM_V2_API.strip()), api='v2'
        ) as server:
            events = await server.get_client().write_events(
                [
                    EventCandidate(
                        source='https://www.eventsourcingdb.io',
                        subject='/books/42',
                        type='io.eventsourcingdb.library.book-acquired',
                        data={'title': 'Dune'},
                    ),
                    EventCandidate(
                        source='https://www.eventsourcingdb.io',
                        subject='/books/42',
                        type='io.eventsourcingdb.library.book-borrowed',
                        data={},
                        trace_parent='00-10000000000000000000000000000000-1000000000000000-00',
                    ),
                ],
            )

            [request] = server.requests
            assert (request.method, request.path) == ('POST', '/api/v2/data/write-events')
            assert json.loads(request.body) == {
                'events': [
                    {
                        'source': 'https://www.eventsourcingdb.io',
                        'subject': '/books/42',
                        'type': 'io.eventsourcingdb.library.book-acquired',
                        'data': {'title': 'Dune'},
                    },
                    {
                        'source': 'https://www.eventsourcingdb.io',
                        'subject': '/books/42',
                        'type': 'io.eventsourcingdb.library.book-borrowed',
                        'data': {},
                        'traceparent': '00-10000000000000000000000000000000-1000000000000000-00',
                    },
                ],
            }

        assert [event.event_id for event in events] == ['0', '1']
        assert events[0].trace_parent is None
        assert events[0].trace_state is None
        assert events[1].trace_state == 'foo=bar'
        for event in events:
            event.verify_hash()

    @staticmethod
    @pytest.mark.asyncio
    async def test_sends_the_preconditions_of_a_write() -> None:
        async with StreamServer(
            answer_with_lines(WRITTEN_EVENTS_FROM_V2_API.strip()), api='v2'
        ) as server:
            await server.get_client().write_events(
                [
                    EventCandidate(
                        source='https://www.eventsourcingdb.io',
                        subject='/books/42',
                        type='io.eventsourcingdb.library.book-acquired',
                        data={},
                    ),
                ],
                [IsSubjectOnEventId('/books/42', '0')],
            )

            assert server.last_request_json()['preconditions'] == [  # type: ignore[index]
                {'type': 'isSubjectOnEventId', 'payload': {'subject': '/books/42', 'eventId': '0'}}
            ]

    @staticmethod
    @pytest.mark.asyncio
    async def test_registers_an_event_schema_with_post() -> None:
        async with StreamServer(
            answer_with_lines(HEARTBEAT, EVENT_SCHEMA_REGISTERED, END), api='v2'
        ) as server:
            await server.get_client().register_event_schema(
                'io.eventsourcingdb.library.book-acquired', {'type': 'object'}
            )

            [request] = server.requests
            assert (request.method, request.path) == ('POST', '/api/v2/data/register-event-schema')
            assert json.loads(request.body) == {
                'type': 'io.eventsourcingdb.library.book-acquired',
                'schema': {'type': 'object'},
            }

    @staticmethod
    @pytest.mark.asyncio
    async def test_fails_to_register_an_event_schema_if_the_server_confirms_nothing() -> None:
        async with StreamServer(answer_with_lines(END), api='v2') as server:
            with pytest.raises(OutcomeUnknownError) as error:
                await server.get_client().register_event_schema(
                    'io.eventsourcingdb.library.book-acquired', {'type': 'object'}
                )

        assert type(error.value.cause) is ServerError
        assert 'Failed to register the event schema' in str(error.value.cause)

    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_an_event_type_with_query() -> None:
        async with StreamServer(answer_with_lines(EVENT_TYPE_WITH_SCHEMA), api='v2') as server:
            event_type = await server.get_client().read_event_type(
                'io.eventsourcingdb.library.book-lent'
            )

            [request] = server.requests
            assert (request.method, request.path) == ('QUERY', '/api/v2/data/read-event-type')
            assert json.loads(request.body) == {'type': 'io.eventsourcingdb.library.book-lent'}

        assert event_type == EventType(
            type='io.eventsourcingdb.library.book-lent',
            has_events=False,
            schema={'type': 'object'},
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_events_with_query() -> None:
        async with StreamServer(
            answer_with_lines(READ_EVENTS_FROM_V2_API[0], HEARTBEAT, READ_EVENTS_FROM_V2_API[1], END),
            api='v2',
        ) as server:
            events = [
                event
                async for event in server.get_client().read_events(
                    '/books/42',
                    ReadEventsOptions(
                        recursive=False,
                        order=Order.ANTICHRONOLOGICAL,
                        lower_bound=Bound(id='0', type=BoundType.INCLUSIVE),
                        upper_bound=Bound(id='5', type=BoundType.EXCLUSIVE),
                    ),
                )
            ]

            [request] = server.requests
            assert (request.method, request.path) == ('QUERY', '/api/v2/data/read-events')
            assert json.loads(request.body) == {
                'subject': '/books/42',
                'options': {
                    'recursive': False,
                    'order': 'antichronological',
                    'lowerBound': {'id': '0', 'type': 'inclusive'},
                    'upperBound': {'id': '5', 'type': 'exclusive'},
                },
            }

        assert [event.event_id for event in events] == ['0', '1']
        for event in events:
            event.verify_hash()

    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_events_from_the_latest_event_without_sending_missing_options() -> None:
        async with StreamServer(answer_with_lines(END), api='v2') as server:
            async for _ in server.get_client().read_events(
                '/books/42',
                ReadEventsOptions(
                    recursive=True,
                    from_latest_event=ReadFromLatestEvent(
                        subject='/books/42',
                        type='io.eventsourcingdb.library.book-borrowed',
                        if_event_is_missing=IfEventIsMissingDuringRead.READ_EVERYTHING,
                    ),
                ),
            ):
                pass

            assert server.last_request_json() == {
                'subject': '/books/42',
                'options': {
                    'recursive': True,
                    'fromLatestEvent': {
                        'subject': '/books/42',
                        'type': 'io.eventsourcingdb.library.book-borrowed',
                        'ifEventIsMissing': 'read-everything',
                    },
                },
            }

    @staticmethod
    @pytest.mark.asyncio
    async def test_observes_events_with_query() -> None:
        async with StreamServer(
            answer_with_lines(HEARTBEAT, READ_EVENTS_FROM_V2_API[0], then_stall=True), api='v2'
        ) as server:
            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                async for event in server.get_client().observe_events(
                    '/books',
                    ObserveEventsOptions(
                        recursive=True,
                        from_latest_event=ObserveFromLatestEvent(
                            subject='/books/42',
                            type='io.eventsourcingdb.library.book-acquired',
                            if_event_is_missing=IfEventIsMissingDuringObserve.WAIT_FOR_EVENT,
                        ),
                    ),
                ):
                    event.verify_hash()
                    break

            [request] = server.requests
            assert (request.method, request.path) == ('QUERY', '/api/v2/data/observe-events')
            assert json.loads(request.body) == {
                'subject': '/books',
                'options': {
                    'recursive': True,
                    'fromLatestEvent': {
                        'subject': '/books/42',
                        'type': 'io.eventsourcingdb.library.book-acquired',
                        'ifEventIsMissing': 'wait-for-event',
                    },
                },
            }

    @staticmethod
    @pytest.mark.asyncio
    async def test_runs_an_eventql_query_with_query_and_returns_the_values_of_the_rows() -> None:
        async with StreamServer(
            answer_with_lines(
                '{"type":"row","data":{"value":{"title":"Dune"}}}',
                HEARTBEAT,
                '{"type":"row","data":{"value":42}}',
                END,
            ),
            api='v2',
        ) as server:
            rows = [
                row
                async for row in server.get_client().run_eventql_query(
                    'FROM e IN events PROJECT INTO e.data'
                )
            ]

            [request] = server.requests
            assert (request.method, request.path) == ('QUERY', '/api/v2/data/run-eventql-query')
            assert json.loads(request.body) == {'query': 'FROM e IN events PROJECT INTO e.data'}

        assert rows == [{'title': 'Dune'}, 42]

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('recursive', [True, False])
    async def test_reads_subjects_with_query_and_sends_whether_recursively(
        recursive: bool,
    ) -> None:
        async with StreamServer(
            answer_with_lines(
                '{"type":"subject","data":{"subject":"/books"}}',
                '{"type":"subject","data":{"subject":"/books/42"}}',
                END,
            ),
            api='v2',
        ) as server:
            subjects = [
                subject
                async for subject in server.get_client().read_subjects(
                    '/books', ReadSubjectsOptions(recursive=recursive)
                )
            ]

            [request] = server.requests
            assert (request.method, request.path) == ('QUERY', '/api/v2/data/read-subjects')
            assert json.loads(request.body) == {
                'subject': '/books',
                'options': {'recursive': recursive},
            }

        # The server decides what to list, the client does not filter.
        assert subjects == ['/books', '/books/42']

    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_event_types_with_query_and_no_body() -> None:
        async with StreamServer(
            answer_with_lines(EVENT_TYPE, EVENT_TYPE_WITH_SCHEMA, END), api='v2'
        ) as server:
            event_types = [event_type async for event_type in server.get_client().read_event_types()]

            [request] = server.requests
            assert (request.method, request.path, request.body) == (
                'QUERY',
                '/api/v2/data/read-event-types',
                b'',
            )

        assert event_types == [
            EventType(type='io.eventsourcingdb.library.book-acquired', has_events=True),
            EventType(
                type='io.eventsourcingdb.library.book-lent',
                has_events=False,
                schema={'type': 'object'},
            ),
        ]

    @staticmethod
    @pytest.mark.asyncio
    async def test_sends_no_null_and_no_unknown_fields() -> None:
        async def make_every_call(client: Client) -> None:
            for parameter in ALL_REQUESTS:
                request_: Request = parameter.values[0]  # type: ignore[assignment]
                try:
                    async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                        await request_(client)
                except (CustomError, TimeoutError):
                    pass

        async with StreamServer(answer_with_lines(END), api='v2') as server:
            await make_every_call(server.get_client())

            bodies = [json.loads(request.body) for request in server.requests if request.body]
            assert len(bodies) == 7
            assert not any(contains_null(body) for body in bodies)


class TestErrorsOfTheV2Api:
    @staticmethod
    @pytest.mark.asyncio
    async def test_reports_an_error_of_a_single_answer_with_its_code_and_details() -> None:
        async with StreamServer(
            answer_with_lines(
                json.dumps({
                    'type': 'error',
                    'data': {
                        'code': 'https://docs.eventsourcingdb.io/errors/event-type-unknown',
                        'description': 'event type is unknown',
                        'details': {'value': 'io.eventsourcingdb.library.book-acquired'},
                    },
                })
            ),
            api='v2',
        ) as server:
            with pytest.raises(DbApiError) as error:
                await read_event_type(server.get_client())

        assert error.value.code == ErrorCode.EVENT_TYPE_UNKNOWN
        assert error.value.description == 'event type is unknown'
        assert error.value.details == {'value': 'io.eventsourcingdb.library.book-acquired'}
        assert error.value.status == 200
        assert error.value.retry_after is None

    @staticmethod
    @pytest.mark.asyncio
    async def test_reports_an_error_in_a_stream_after_the_items_before_it() -> None:
        async with StreamServer(
            answer_with_lines(READ_EVENTS_FROM_V2_API[0], ERROR, END), api='v2'
        ) as server:
            events = []
            with pytest.raises(DbApiError) as error:
                async for event in server.get_client().read_events(
                    '/books/42', ReadEventsOptions(recursive=False)
                ):
                    events.append(event)

        assert len(events) == 1
        assert error.value.code == ErrorCode.PRECONDITION_VIOLATED
        assert error.value.details == {'precondition': 0}
        assert error.value.status == 200

    @staticmethod
    @pytest.mark.asyncio
    async def test_reports_a_code_the_client_does_not_know_exactly_as_sent() -> None:
        code = 'https://docs.eventsourcingdb.io/errors/something-new'
        async with StreamServer(
            answer_with_lines(
                json.dumps({'type': 'error', 'data': {'code': code, 'description': 'x', 'details': {}}}),
                END,
            ),
            api='v2',
        ) as server:
            with pytest.raises(DbApiError) as error:
                await read_events(server.get_client())

        assert error.value.code == code

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('request_', REQUESTS_EXCEPT_PING)
    @pytest.mark.parametrize(
        ('status', 'text'),
        [
            pytest.param(400, '/events/0/traceparent: null is not allowed', id='400'),
            pytest.param(401, 'unauthorized', id='401'),
            pytest.param(413, 'request body too large', id='413'),
            pytest.param(503, 'server is shutting down', id='503'),
        ],
    )
    async def test_reports_another_status_with_its_text_and_without_a_code(
        request_: Request, status: int, text: str
    ) -> None:
        async with StreamServer(
            answer_with_lines(text),
            status=status,
            headers={'Content-Type': 'text/plain; charset=utf-8'},
            api='v2',
        ) as server:
            with pytest.raises(DbApiError) as error:
                await request_(server.get_client())

        assert (error.value.status, error.value.description, error.value.code) == (
            status,
            text,
            None,
        )
        assert error.value.details == {}

    @staticmethod
    @pytest.mark.asyncio
    async def test_tells_the_seconds_of_the_retry_after_header_of_a_429() -> None:
        async with StreamServer(
            answer_with_lines('too many requests'),
            status=429,
            headers={'Content-Type': 'text/plain; charset=utf-8', 'Retry-After': '3'},
            api='v2',
        ) as server:
            with pytest.raises(DbApiError) as error:
                await read_events(server.get_client())

        assert (error.value.status, error.value.retry_after) == (429, 3)

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('request_', REQUESTS_EXCEPT_PING)
    async def test_fails_if_the_answer_is_not_from_eventsourcingdb(request_: Request) -> None:
        async with StreamServer(
            answer_with_lines(END), api='v2', headers={'Server': None}
        ) as server:
            with pytest.raises((ServerError, OutcomeUnknownError)) as error:
                await request_(server.get_client())

        # A write may have been stored by a server behind whatever answered.
        reported_error: BaseException = error.value
        if isinstance(reported_error, OutcomeUnknownError):
            assert request_ in {write.values[0] for write in WRITES}
            reported_error = reported_error.cause
        assert 'Server must be EventSourcingDB' in str(reported_error)

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'request_',
        STREAMS
        + [
            pytest.param(run_eventql_query, id='run_eventql_query'),
            pytest.param(observe_events, id='observe_events'),
        ],
    )
    async def test_fails_on_an_item_of_an_unexpected_type(request_: Request) -> None:
        async with StreamServer(
            answer_with_lines('{"type":"surprise","data":{}}', END), api='v2'
        ) as server:
            with pytest.raises(ServerError, match='unexpected item') as error:
                await request_(server.get_client())

        assert type(error.value) is ServerError

    @staticmethod
    @pytest.mark.asyncio
    async def test_fails_on_a_line_that_is_not_an_envelope() -> None:
        async with StreamServer(answer_with_lines('{"type":"event"}', END), api='v2') as server:
            with pytest.raises(ServerError, match='unexpected answer'):
                await read_events(server.get_client())


class TestStreamsOfTheV2ApiThatBreakOff:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ('request_', 'lines'),
        [
            pytest.param(read_events, [READ_EVENTS_FROM_V2_API[0]], id='read_events'),
            pytest.param(
                read_subjects,
                ['{"type":"subject","data":{"subject":"/books"}}'],
                id='read_subjects',
            ),
            pytest.param(read_event_types, [EVENT_TYPE], id='read_event_types'),
            pytest.param(
                run_eventql_query, ['{"type":"row","data":{"value":1}}'], id='run_eventql_query'
            ),
            pytest.param(observe_events, [READ_EVENTS_FROM_V2_API[0]], id='observe_events'),
            pytest.param(observe_events, [], id='observe_events without events'),
        ],
    )
    async def test_fails_if_the_stream_ends_without_its_end_item(
        request_: Request, lines: list[str]
    ) -> None:
        async with StreamServer(answer_with_lines(*lines, HEARTBEAT), api='v2') as server:
            with pytest.raises(ServerError, match='closed the stream before it ended') as error:
                await request_(server.get_client())

        assert type(error.value) is ServerError

    @staticmethod
    @pytest.mark.asyncio
    async def test_fails_if_an_observation_ends() -> None:
        # An observation never ends, so an end item is as unexpected as any
        # other item that is not an event.
        async with StreamServer(answer_with_lines(END), api='v2') as server:
            with pytest.raises(ServerError, match='unexpected item'):
                await observe_events(server.get_client())

    @staticmethod
    @pytest.mark.asyncio
    async def test_stops_reading_at_the_end_item() -> None:
        async with StreamServer(
            answer_with_lines(READ_EVENTS_FROM_V2_API[0], END, READ_EVENTS_FROM_V2_API[1]),
            api='v2',
        ) as server:
            events = [
                event
                async for event in server.get_client().read_events(
                    '/books/42', ReadEventsOptions(recursive=False)
                )
            ]

        assert [event.event_id for event in events] == ['0']

