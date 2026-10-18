import asyncio
import math
import socket
import time
from typing import Any

import aiohttp
import aiohttp.client
import aiohttp.connector
import pytest
from aiohttp import web

from eventsourcingdb import (
    Client,
    ConnectionStalledError,
    EventCandidate,
    OutcomeUnknownError,
    ReadEventsOptions,
    ReadSubjectsOptions,
    ServerError,
)
from eventsourcingdb.http_client import DEFAULT_STALL_TIMEOUT_SECONDS
from eventsourcingdb.http_client.response import MAX_LINE_BYTES

from .event.fixtures import (
    READ_EVENTS_FROM_V2_API,
    READ_EVENTS_WITH_HASH_V2,
    WRITTEN_EVENTS_FROM_V2_API,
    WRITTEN_EVENTS_WITH_HASH_V2,
)
from .shared.requests import (
    ALL_REQUESTS,
    Request,
    observe_events,
    observe_first_event,
    ping,
    read_event_types,
    read_events,
    run_eventql_query,
    write_events,
)
from .shared.stream_server import Api, StreamServer

STALL_TIMEOUT_SECONDS = 0.5
GUARD_TIMEOUT_SECONDS = 5

HEARTBEAT_LINE = b'{"type":"heartbeat","payload":{}}\n'
ROW_LINE = b'{"type":"row","payload":{"title":"Dune"}}\n'
V2_HEARTBEAT_LINE = b'{"type":"heartbeat","data":{}}\n'
V2_END_LINE = b'{"type":"end","data":{}}\n'
APIS: list[Api] = ['v1', 'v2']

REQUESTS = {parameter.id: parameter.values[0] for parameter in ALL_REQUESTS}

# Partial responses per API, after which the server stalls. register_event_schema
# does not read the body of a successful response of the v1 API, so it has none.
PARTIAL_RESPONSES: dict[Api, dict[str, bytes]] = {
    'v1': {
        'ping': b'{"specversion":',
        'verify_api_token': b'{"type":',
        'write_events': b'[',
        'read_event_type': b'{"eventType":',
        'read_events': b'{"type":"event",',
        'read_subjects': b'{"type":"subject",',
        'read_event_types': b'{"type":"eventType",',
        'observe_events': HEARTBEAT_LINE,
        'run_eventql_query': HEARTBEAT_LINE,
    },
    'v2': {
        'ping': b'{"type":"event","data":{"specversion":',
        'verify_api_token': b'{"type":',
        'write_events': V2_HEARTBEAT_LINE,
        'register_event_schema': V2_HEARTBEAT_LINE + b'{"type":"event",',
        'read_event_type': b'{"type":"eventType",',
        'read_events': V2_HEARTBEAT_LINE + b'{"type":"event",',
        'read_subjects': b'{"type":"subject",',
        'read_event_types': b'{"type":"eventType",',
        'observe_events': V2_HEARTBEAT_LINE,
        'run_eventql_query': V2_HEARTBEAT_LINE,
    },
}

# Complete responses per API, which the server sends in parts.
COMPLETE_RESPONSES: dict[Api, dict[str, bytes]] = {
    'v1': {
        'ping': b'{"specversion":"1.0","type":"io.eventsourcingdb.api.ping-received"}',
        'verify_api_token': b'{"type":"io.eventsourcingdb.api.api-token-verified"}',
        'write_events': WRITTEN_EVENTS_WITH_HASH_V2.encode('utf-8'),
        'read_event_type': (
            b'{"eventType":"io.eventsourcingdb.library.book-acquired","isPhantom":false}'
        ),
        'read_events': READ_EVENTS_WITH_HASH_V2[0].encode('utf-8') + b'\n',
        'read_subjects': b'{"type":"subject","payload":{"subject":"/books/42"}}\n',
        'read_event_types': (
            b'{"type":"eventType","payload":'
            b'{"eventType":"io.eventsourcingdb.library.book-acquired","isPhantom":false}}\n'
        ),
        'observe_events': READ_EVENTS_WITH_HASH_V2[0].encode('utf-8') + b'\n',
        'run_eventql_query': ROW_LINE,
    },
    'v2': {
        'ping': b'{"type":"event","data":{"type":"io.eventsourcingdb.api.ping-received"}}',
        'verify_api_token': (
            b'{"type":"event","data":{"type":"io.eventsourcingdb.api.token-verified"}}'
        ),
        'write_events': WRITTEN_EVENTS_FROM_V2_API.encode('utf-8'),
        'register_event_schema': (
            b'{"type":"event","data":'
            b'{"type":"io.eventsourcingdb.api.event-schema-registered"}}\n' + V2_END_LINE
        ),
        'read_event_type': (
            b'{"type":"eventType","data":{"type":"io.eventsourcingdb.library.book-acquired",'
            b'"hasEvents":true,"schema":null}}'
        ),
        'read_events': READ_EVENTS_FROM_V2_API[0].encode('utf-8') + b'\n' + V2_END_LINE,
        'read_subjects': b'{"type":"subject","data":{"subject":"/books/42"}}\n' + V2_END_LINE,
        'read_event_types': (
            b'{"type":"eventType","data":{"type":"io.eventsourcingdb.library.book-acquired",'
            b'"hasEvents":true,"schema":null}}\n' + V2_END_LINE
        ),
        'observe_events': READ_EVENTS_FROM_V2_API[0].encode('utf-8') + b'\n',
        'run_eventql_query': b'{"type":"row","data":{"value":{"title":"Dune"}}}\n' + V2_END_LINE,
    },
}

# Observing never ends, so a request that is complete stops at an event.
COMPLETE_REQUESTS = {**REQUESTS, 'observe_events': observe_first_event}


def per_api(names: list[str] | None = None) -> list[Any]:
    return [
        pytest.param(api, REQUESTS[name], id=f'{api}, {name}')
        for api in APIS
        for name in (names or REQUESTS)
    ]


WRITE_NAMES = {'write_events', 'register_event_schema'}


def assert_stalled(error: BaseException, name: str) -> None:
    # A write that stalls once it has a connection may have been stored, so
    # its outcome is unknown.
    if name in WRITE_NAMES:
        assert type(error) is OutcomeUnknownError
        error = error.cause

    assert type(error) is ConnectionStalledError


def name_of(request_: Request) -> str:
    return next(name for name, known_request in REQUESTS.items() if known_request is request_)


def stream_server(write_stream: Any, api: Api, **options: Any) -> StreamServer:
    # Only the first ping asks whether the server offers the v2 API, so that a
    # ping of the v2 API reaches the stream as every other request does.
    return StreamServer(
        write_stream,
        stall_timeout=STALL_TIMEOUT_SECONDS,
        api=api,
        answers_only_first_probe=True,
        **options,
    )


async def stall() -> None:
    await asyncio.Event().wait()


async def write_in_parts(response: web.StreamResponse, content: bytes) -> None:
    # Six parts, each well within the stall timeout, take longer than twice
    # the stall timeout in total.
    part_count = 6
    part_size = -(-len(content) // part_count)
    for start in range(0, len(content), part_size):
        await response.write(content[start:start + part_size])
        await asyncio.sleep(STALL_TIMEOUT_SECONDS * 0.4)


@pytest.fixture
def single_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    # Lets a client open only one connection at a time, so that a second
    # request waits for a free connection of the pool.
    class SingleConnectionConnector(aiohttp.TCPConnector):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, limit=1, **kwargs)

    monkeypatch.setattr(aiohttp.client, 'TCPConnector', SingleConnectionConnector)


class HangingResolver(aiohttp.abc.AbstractResolver):
    def __init__(self, *_: Any, **__: Any) -> None:
        pass

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[aiohttp.abc.ResolveResult]:
        await stall()
        return []

    async def close(self) -> None:
        pass


class TestStallTimeout:
    @staticmethod
    def test_is_30_seconds_by_default() -> None:
        assert DEFAULT_STALL_TIMEOUT_SECONDS == 30

    @staticmethod
    @pytest.mark.parametrize(
        'stall_timeout',
        [
            pytest.param(0, id='zero'),
            pytest.param(-1, id='negative'),
            pytest.param(math.inf, id='infinite'),
            pytest.param(-math.inf, id='negative infinite'),
            pytest.param(math.nan, id='not a number'),
        ],
    )
    def test_rejects_a_stall_timeout_that_is_not_a_finite_number_greater_than_zero(
        stall_timeout: float,
    ) -> None:
        with pytest.raises(ValueError, match='The stall timeout must be a finite number'):
            Client('http://localhost:3000', 'secret', stall_timeout=stall_timeout)

    @staticmethod
    def test_accepts_a_stall_timeout_that_is_a_finite_number_greater_than_zero() -> None:
        Client('http://localhost:3000', 'secret', stall_timeout=0.001)

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'request_'), per_api())
    async def test_fails_if_the_server_does_not_answer_within_the_stall_timeout(
        api: Api, request_: Request
    ) -> None:
        async with stream_server(None, api) as server:
            started_at = time.monotonic()

            with pytest.raises((ConnectionStalledError, OutcomeUnknownError)) as error:
                async with asyncio.timeout(GUARD_TIMEOUT_SECONDS) as guard:
                    await request_(server.get_client())

            elapsed_seconds = time.monotonic() - started_at
            assert not guard.expired()
            assert_stalled(error.value, name_of(request_))
            assert elapsed_seconds >= STALL_TIMEOUT_SECONDS
            assert elapsed_seconds < STALL_TIMEOUT_SECONDS + 1

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ('api', 'name'),
        [
            pytest.param(api, name, id=f'{api}, {name}')
            for api in APIS
            for name in PARTIAL_RESPONSES[api]
        ],
    )
    async def test_fails_if_the_server_stalls_while_answering(api: Api, name: str) -> None:
        async def write_stream(response: web.StreamResponse) -> None:
            await response.write(PARTIAL_RESPONSES[api][name])
            await stall()

        async with stream_server(write_stream, api) as server:
            started_at = time.monotonic()

            with pytest.raises((ConnectionStalledError, OutcomeUnknownError)) as error:
                async with asyncio.timeout(GUARD_TIMEOUT_SECONDS) as guard:
                    await REQUESTS[name](server.get_client())

            elapsed_seconds = time.monotonic() - started_at
            assert not guard.expired()
            assert_stalled(error.value, name)
            assert elapsed_seconds >= STALL_TIMEOUT_SECONDS
            assert elapsed_seconds < STALL_TIMEOUT_SECONDS + 1

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await server.client_disconnected.wait()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ('api', 'name'),
        [
            pytest.param(api, name, id=f'{api}, {name}')
            for api in APIS
            for name in COMPLETE_RESPONSES[api]
        ],
    )
    async def test_keeps_a_request_going_while_parts_of_the_response_arrive(
        api: Api, name: str
    ) -> None:
        async def write_stream(response: web.StreamResponse) -> None:
            await write_in_parts(response, COMPLETE_RESPONSES[api][name])

        async with stream_server(write_stream, api) as server:
            started_at = time.monotonic()

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await COMPLETE_REQUESTS[name](server.get_client())

            assert time.monotonic() - started_at > 2 * STALL_TIMEOUT_SECONDS

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('api', APIS)
    async def test_does_not_count_the_time_the_caller_spends_between_two_items(api: Api) -> None:
        lines = READ_EVENTS_WITH_HASH_V2 if api == 'v1' else READ_EVENTS_FROM_V2_API

        async def write_stream(response: web.StreamResponse) -> None:
            for line in lines:
                await response.write(line.encode('utf-8') + b'\n')
                await asyncio.sleep(STALL_TIMEOUT_SECONDS / 5)
            if api == 'v2':
                await response.write(V2_END_LINE)

        async with stream_server(write_stream, api) as server:
            events = []

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                async for event in server.get_client().read_events(
                    '/books/42', ReadEventsOptions(recursive=False)
                ):
                    events.append(event)
                    await asyncio.sleep(2 * STALL_TIMEOUT_SECONDS)

            assert len(events) == len(lines)

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'request_'), per_api())
    async def test_does_not_replace_a_timeout_of_the_caller(api: Api, request_: Request) -> None:
        async with stream_server(None, api) as server:
            with pytest.raises((TimeoutError, OutcomeUnknownError)) as error:
                async with asyncio.timeout(STALL_TIMEOUT_SECONDS / 2) as deadline:
                    await request_(server.get_client())

            assert deadline.expired()
            # A write that the caller ends once it has a connection may have
            # been stored, so its outcome is unknown.
            if name_of(request_) in WRITE_NAMES:
                assert type(error.value) is OutcomeUnknownError
                assert isinstance(error.value.cause, asyncio.CancelledError)
            else:
                assert type(error.value) is TimeoutError

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.usefixtures('short_session_timeout')
    @pytest.mark.parametrize(
        ('api', 'name'),
        [
            pytest.param(api, name, id=f'{api}, {name}')
            for api in APIS
            for name in ['ping', 'write_events']
        ],
    )
    async def test_does_not_end_a_request_at_the_timeout_of_the_session(
        api: Api, name: str
    ) -> None:
        async def write_stream(response: web.StreamResponse) -> None:
            await asyncio.sleep(1.5)
            await response.write(COMPLETE_RESPONSES[api][name])

        # The client uses the default stall timeout, while aiohttp's default
        # session timeout, which the fixture shortened to one second, would
        # end the request before the response arrives.
        async with StreamServer(write_stream, api=api, answers_only_first_probe=True) as server:
            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await REQUESTS[name](server.get_client())

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'request_',
        [
            pytest.param(ping, id='ping'),
            pytest.param(write_events, id='write_events'),
            pytest.param(read_events, id='read_events'),
            pytest.param(observe_events, id='observe_events'),
            pytest.param(read_event_types, id='read_event_types'),
        ],
    )
    async def test_fails_with_a_stalled_connection_if_connecting_stalls(
        monkeypatch: pytest.MonkeyPatch, request_: Request
    ) -> None:
        monkeypatch.setattr(aiohttp.connector, 'DefaultResolver', HangingResolver)

        async with Client(
            'http://eventsourcingdb.test:3000', 'secret', stall_timeout=STALL_TIMEOUT_SECONDS
        ) as client:
            started_at = time.monotonic()

            with pytest.raises(ConnectionStalledError) as error:
                async with asyncio.timeout(GUARD_TIMEOUT_SECONDS) as guard:
                    await request_(client)

            elapsed_seconds = time.monotonic() - started_at
            assert not guard.expired()
            assert type(error.value) is ConnectionStalledError
            assert elapsed_seconds >= STALL_TIMEOUT_SECONDS
            assert elapsed_seconds < STALL_TIMEOUT_SECONDS + 1

    @staticmethod
    @pytest.mark.asyncio
    async def test_fails_if_the_server_does_not_take_the_request() -> None:
        connection_count = 0

        async def answer_probe_then_never_read(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            nonlocal connection_count
            connection_count += 1

            # The first connection carries the ping that the client asks with
            # whether the server offers the v2 API, which it does not.
            if connection_count == 1:
                await reader.readuntil(b'\r\n\r\n')
                writer.write(
                    b'HTTP/1.1 404 Not Found\r\nServer: EventSourcingDB/test\r\n'
                    b'Content-Length: 0\r\nConnection: close\r\n\r\n'
                )
                await writer.drain()
                writer.close()
                return

            await stall()

        server = await asyncio.start_server(answer_probe_then_never_read, '127.0.0.1', 0)
        port = server.sockets[0].getsockname()[1]

        try:
            async with Client(
                f'http://127.0.0.1:{port}', 'secret', stall_timeout=STALL_TIMEOUT_SECONDS
            ) as client:
                with pytest.raises(OutcomeUnknownError) as error:
                    async with asyncio.timeout(GUARD_TIMEOUT_SECONDS) as guard:
                        # Far more data than the buffers of the connection hold,
                        # so that sending stalls once they are full.
                        await client.write_events(
                            [
                                EventCandidate(
                                    source='https://www.eventsourcingdb.io',
                                    subject='/books/42',
                                    type='io.eventsourcingdb.library.book-acquired',
                                    data={'text': 'x' * 64 * 1024 * 1024},
                                )
                            ]
                        )

                assert not guard.expired()
                assert_stalled(error.value, 'write_events')
                assert connection_count == 2
        finally:
            server.close()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ('api', 'request_'), per_api(['ping', 'write_events', 'read_events', 'observe_events'])
    )
    async def test_fails_if_a_request_waits_for_a_free_connection_for_longer_than_the_stall_timeout(
        single_connection: None, api: Api, request_: Request
    ) -> None:
        heartbeat_line = HEARTBEAT_LINE if api == 'v1' else V2_HEARTBEAT_LINE

        async def write_stream(response: web.StreamResponse) -> None:
            # The first query keeps the only connection busy for good.
            while True:
                await response.write(heartbeat_line)
                await asyncio.sleep(STALL_TIMEOUT_SECONDS / 5)

        async with stream_server(write_stream, api) as server:
            client = server.get_client()
            busy_query = asyncio.create_task(run_eventql_query(client))
            await asyncio.sleep(STALL_TIMEOUT_SECONDS / 5)

            try:
                started_at = time.monotonic()

                with pytest.raises(ConnectionStalledError) as error:
                    async with asyncio.timeout(GUARD_TIMEOUT_SECONDS) as guard:
                        await request_(client)

                elapsed_seconds = time.monotonic() - started_at
                assert not guard.expired()
                assert type(error.value) is ConnectionStalledError
                assert elapsed_seconds >= STALL_TIMEOUT_SECONDS
                assert elapsed_seconds < STALL_TIMEOUT_SECONDS + 1
            finally:
                busy_query.cancel()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('api', APIS)
    async def test_sends_a_request_that_gets_a_free_connection_within_the_stall_timeout(
        single_connection: None, api: Api
    ) -> None:
        request_count = 0
        heartbeat_line = HEARTBEAT_LINE if api == 'v1' else V2_HEARTBEAT_LINE

        async def write_stream(response: web.StreamResponse) -> None:
            nonlocal request_count
            request_count += 1

            # The first query keeps the only connection busy for a while, the
            # second one answers with a row as soon as it gets the connection.
            if request_count == 1:
                for _ in range(3):
                    await response.write(heartbeat_line)
                    await asyncio.sleep(STALL_TIMEOUT_SECONDS / 5)
            await response.write(COMPLETE_RESPONSES[api]['run_eventql_query'])

        async with stream_server(write_stream, api) as server:
            client = server.get_client()

            first_query = asyncio.create_task(run_eventql_query(client))
            await asyncio.sleep(STALL_TIMEOUT_SECONDS / 10)

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await run_eventql_query(client)
                await first_query

            assert request_count == 2


def subject_line(api: Api, subject: str) -> bytes:
    key = 'payload' if api == 'v1' else 'data'
    return ('{"type":"subject","' + key + '":{"subject":"' + subject + '"}}\n').encode('utf-8')


class TestLineLength:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ('api', 'request_'),
        per_api(['read_events', 'read_subjects', 'read_event_types', 'observe_events', 'run_eventql_query']),
    )
    async def test_fails_if_a_line_does_not_end_within_the_limit(api: Api, request_: Request) -> None:
        # The parts keep arriving, so only the limit can end the response.
        async def write_stream(response: web.StreamResponse) -> None:
            part = b'x' * 65536
            for _ in range(2 * MAX_LINE_BYTES // len(part)):
                await response.write(part)
            await stall()

        async with stream_server(write_stream, api) as server:
            with pytest.raises(ServerError, match=f'longer than {MAX_LINE_BYTES} bytes') as error:
                async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                    await request_(server.get_client())

            assert type(error.value) is ServerError

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('api', APIS)
    async def test_fails_if_a_complete_line_is_longer_than_the_limit(api: Api) -> None:
        line = subject_line(api, '/' + 'a' * MAX_LINE_BYTES)

        async def write_stream(response: web.StreamResponse) -> None:
            await response.write(line)

        async with stream_server(write_stream, api) as server:
            with pytest.raises(ServerError, match=f'longer than {MAX_LINE_BYTES} bytes'):
                async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                    async for _ in server.get_client().read_subjects(
                        '/', ReadSubjectsOptions(recursive=True)
                    ):
                        pass

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('api', APIS)
    async def test_reads_a_line_within_the_limit(api: Api) -> None:
        subject = '/' + 'a' * (MAX_LINE_BYTES - 100)
        line = subject_line(api, subject)

        async def write_stream(response: web.StreamResponse) -> None:
            await write_in_parts(response, line + (V2_END_LINE if api == 'v2' else b''))

        async with stream_server(write_stream, api) as server:
            subjects = []
            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                async for read_subject in server.get_client().read_subjects(
                    '/', ReadSubjectsOptions(recursive=True)
                ):
                    subjects.append(read_subject)

            assert subjects == [subject]
