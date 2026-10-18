import asyncio
import math
import socket
import time
from collections.abc import Awaitable, Callable
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
    HeartbeatTimeoutError,
    InternalError,
    ObserveEventsOptions,
    ReadEventsOptions,
)
from eventsourcingdb.http_client import DEFAULT_STALL_TIMEOUT_SECONDS

from .event.fixtures import READ_EVENTS_WITH_HASH_V2, WRITTEN_EVENTS_WITH_HASH_V2
from .shared.stream_server import StreamServer

STALL_TIMEOUT_SECONDS = 0.5
GUARD_TIMEOUT_SECONDS = 5

HEARTBEAT_LINE = b'{"type":"heartbeat","payload":{}}\n'
ROW_LINE = b'{"type":"row","payload":{"title":"Dune"}}\n'

Request = Callable[[Client], Awaitable[None]]


async def ping(client: Client) -> None:
    await client.ping()


async def verify_api_token(client: Client) -> None:
    await client.verify_api_token()


async def write_events(client: Client) -> None:
    await client.write_events(
        [
            EventCandidate(
                source='https://www.eventsourcingdb.io',
                subject='/books/42',
                type='io.eventsourcingdb.library.book-acquired',
                data={},
            )
        ]
    )


async def register_event_schema(client: Client) -> None:
    await client.register_event_schema(
        'io.eventsourcingdb.library.book-acquired', {'type': 'object'}
    )


async def read_event_type(client: Client) -> None:
    await client.read_event_type('io.eventsourcingdb.library.book-acquired')


async def read_events(client: Client) -> None:
    async for _ in client.read_events('/', ReadEventsOptions(recursive=True)):
        pass


async def read_subjects(client: Client) -> None:
    async for _ in client.read_subjects('/'):
        pass


async def read_event_types(client: Client) -> None:
    async for _ in client.read_event_types():
        pass


async def observe_events(client: Client) -> None:
    async for _ in client.observe_events('/', ObserveEventsOptions(recursive=True)):
        pass


async def run_eventql_query(client: Client) -> None:
    async for _ in client.run_eventql_query('FROM e IN events PROJECT INTO e'):
        pass


# Before there was a stall timeout, a stalling request that is not a stream
# ended with a TimeoutError after five minutes, so it still does. A stream
# waited forever, so it ends with a ConnectionStalledError, or, once the
# response has arrived, with a HeartbeatTimeoutError if it sends heartbeats.
ONE_SHOT_REQUESTS = [
    pytest.param(ping, id='ping'),
    pytest.param(verify_api_token, id='verify_api_token'),
    pytest.param(write_events, id='write_events'),
    pytest.param(register_event_schema, id='register_event_schema'),
    pytest.param(read_event_type, id='read_event_type'),
]
STREAMS = [
    pytest.param(read_events, id='read_events'),
    pytest.param(read_subjects, id='read_subjects'),
    pytest.param(read_event_types, id='read_event_types'),
]
HEARTBEAT_STREAMS = [
    pytest.param(observe_events, id='observe_events'),
    pytest.param(run_eventql_query, id='run_eventql_query'),
]

# Partial responses, after which the server stalls. register_event_schema does
# not read the body of a successful response, so it has none.
PARTIAL_RESPONSES = [
    pytest.param(ping, b'{"specversion":', TimeoutError, id='ping'),
    pytest.param(verify_api_token, b'{"type":', TimeoutError, id='verify_api_token'),
    pytest.param(write_events, b'[', TimeoutError, id='write_events'),
    pytest.param(read_event_type, b'{"eventType":', TimeoutError, id='read_event_type'),
    pytest.param(read_events, b'{"type":"event",', ConnectionStalledError, id='read_events'),
    pytest.param(read_subjects, b'{"type":"subject",', ConnectionStalledError, id='read_subjects'),
    pytest.param(
        read_event_types, b'{"type":"eventType",', ConnectionStalledError, id='read_event_types'
    ),
    pytest.param(observe_events, HEARTBEAT_LINE, HeartbeatTimeoutError, id='observe_events'),
    pytest.param(run_eventql_query, HEARTBEAT_LINE, HeartbeatTimeoutError, id='run_eventql_query'),
]

# Complete responses, which the server sends in parts.
COMPLETE_RESPONSES = [
    pytest.param(
        ping,
        b'{"specversion":"1.0","type":"io.eventsourcingdb.api.ping-received"}',
        id='ping',
    ),
    pytest.param(
        verify_api_token,
        b'{"type":"io.eventsourcingdb.api.api-token-verified"}',
        id='verify_api_token',
    ),
    pytest.param(write_events, WRITTEN_EVENTS_WITH_HASH_V2.encode('utf-8'), id='write_events'),
    pytest.param(
        read_event_type,
        b'{"eventType":"io.eventsourcingdb.library.book-acquired","isPhantom":false}',
        id='read_event_type',
    ),
    pytest.param(
        read_events, READ_EVENTS_WITH_HASH_V2[0].encode('utf-8') + b'\n', id='read_events'
    ),
    pytest.param(
        read_subjects, b'{"type":"subject","payload":{"subject":"/books/42"}}\n', id='read_subjects'
    ),
    pytest.param(
        read_event_types,
        b'{"type":"eventType","payload":'
        b'{"eventType":"io.eventsourcingdb.library.book-acquired","isPhantom":false}}\n',
        id='read_event_types',
    ),
    pytest.param(
        observe_events, READ_EVENTS_WITH_HASH_V2[0].encode('utf-8') + b'\n', id='observe_events'
    ),
    pytest.param(run_eventql_query, ROW_LINE, id='run_eventql_query'),
]


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
    @pytest.mark.parametrize(
        ('request_', 'expected_error'),
        [pytest.param(*parameter.values, TimeoutError, id=parameter.id) for parameter in ONE_SHOT_REQUESTS]
        + [
            pytest.param(*parameter.values, ConnectionStalledError, id=parameter.id)
            for parameter in STREAMS + HEARTBEAT_STREAMS
        ],
    )
    async def test_fails_if_the_server_does_not_answer_within_the_stall_timeout(
        request_: Request, expected_error: type[Exception]
    ) -> None:
        async with StreamServer(None, stall_timeout=STALL_TIMEOUT_SECONDS) as server:
            started_at = time.monotonic()

            with pytest.raises(expected_error) as error:
                async with asyncio.timeout(GUARD_TIMEOUT_SECONDS) as guard:
                    await request_(server.get_client())

            elapsed_seconds = time.monotonic() - started_at
            assert not guard.expired()
            assert type(error.value) is expected_error
            assert elapsed_seconds >= STALL_TIMEOUT_SECONDS
            assert elapsed_seconds < STALL_TIMEOUT_SECONDS + 1

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('request_', 'partial_response', 'expected_error'), PARTIAL_RESPONSES)
    async def test_fails_if_the_server_stalls_while_answering(
        request_: Request, partial_response: bytes, expected_error: type[Exception]
    ) -> None:
        async def write_stream(response: web.StreamResponse) -> None:
            await response.write(partial_response)
            await stall()

        async with StreamServer(write_stream, stall_timeout=STALL_TIMEOUT_SECONDS) as server:
            started_at = time.monotonic()

            with pytest.raises(expected_error) as error:
                async with asyncio.timeout(GUARD_TIMEOUT_SECONDS) as guard:
                    await request_(server.get_client())

            elapsed_seconds = time.monotonic() - started_at
            assert not guard.expired()
            assert type(error.value) is expected_error
            assert elapsed_seconds >= STALL_TIMEOUT_SECONDS
            assert elapsed_seconds < STALL_TIMEOUT_SECONDS + 1

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await server.client_disconnected.wait()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('request_', 'complete_response'), COMPLETE_RESPONSES)
    async def test_keeps_a_request_going_while_parts_of_the_response_arrive(
        request_: Request, complete_response: bytes
    ) -> None:
        async def write_stream(response: web.StreamResponse) -> None:
            await write_in_parts(response, complete_response)

        async with StreamServer(write_stream, stall_timeout=STALL_TIMEOUT_SECONDS) as server:
            started_at = time.monotonic()

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await request_(server.get_client())

            assert time.monotonic() - started_at > 2 * STALL_TIMEOUT_SECONDS

    @staticmethod
    @pytest.mark.asyncio
    async def test_does_not_count_the_time_the_caller_spends_between_two_items() -> None:
        async def write_stream(response: web.StreamResponse) -> None:
            for line in READ_EVENTS_WITH_HASH_V2:
                await response.write(line.encode('utf-8') + b'\n')
                await asyncio.sleep(STALL_TIMEOUT_SECONDS / 5)

        async with StreamServer(write_stream, stall_timeout=STALL_TIMEOUT_SECONDS) as server:
            events = []

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                async for event in server.get_client().read_events(
                    '/books/42', ReadEventsOptions(recursive=False)
                ):
                    events.append(event)
                    await asyncio.sleep(2 * STALL_TIMEOUT_SECONDS)

            assert len(events) == len(READ_EVENTS_WITH_HASH_V2)

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'request_', ONE_SHOT_REQUESTS + STREAMS + HEARTBEAT_STREAMS
    )
    async def test_does_not_replace_a_timeout_of_the_caller(request_: Request) -> None:
        async with StreamServer(None, stall_timeout=STALL_TIMEOUT_SECONDS) as server:
            with pytest.raises(TimeoutError) as error:
                async with asyncio.timeout(STALL_TIMEOUT_SECONDS / 2) as deadline:
                    await request_(server.get_client())

            assert deadline.expired()
            assert type(error.value) is TimeoutError

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.usefixtures('short_session_timeout')
    @pytest.mark.parametrize(
        ('request_', 'complete_response'),
        [parameter for parameter in COMPLETE_RESPONSES if parameter.id in {'ping', 'write_events'}],
    )
    async def test_does_not_end_a_request_at_the_timeout_of_the_session(
        request_: Request, complete_response: bytes
    ) -> None:
        async def write_stream(response: web.StreamResponse) -> None:
            await asyncio.sleep(1.5)
            await response.write(complete_response)

        # The client uses the default stall timeout, while aiohttp's default
        # session timeout, which the fixture shortened to one second, would
        # end the request before the response arrives.
        async with StreamServer(write_stream) as server:
            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await request_(server.get_client())

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ('request_', 'expected_error'),
        [
            pytest.param(ping, aiohttp.ConnectionTimeoutError, id='ping'),
            pytest.param(write_events, aiohttp.ConnectionTimeoutError, id='write_events'),
            pytest.param(read_events, aiohttp.ConnectionTimeoutError, id='read_events'),
            pytest.param(observe_events, aiohttp.ConnectionTimeoutError, id='observe_events'),
            # Reading event types wraps any error that is not one of the client
            # SDK in an InternalError, as it does for every connection error.
            pytest.param(read_event_types, InternalError, id='read_event_types'),
        ],
    )
    async def test_fails_with_a_connection_timeout_if_connecting_stalls(
        monkeypatch: pytest.MonkeyPatch, request_: Request, expected_error: type[Exception]
    ) -> None:
        monkeypatch.setattr(aiohttp.connector, 'DefaultResolver', HangingResolver)

        async with Client(
            'http://eventsourcingdb.test:3000', 'secret', stall_timeout=STALL_TIMEOUT_SECONDS
        ) as client:
            started_at = time.monotonic()

            with pytest.raises(expected_error) as error:
                async with asyncio.timeout(GUARD_TIMEOUT_SECONDS) as guard:
                    await request_(client)

            elapsed_seconds = time.monotonic() - started_at
            assert not guard.expired()
            assert elapsed_seconds >= STALL_TIMEOUT_SECONDS
            assert elapsed_seconds < STALL_TIMEOUT_SECONDS + 1
            if expected_error is InternalError:
                assert isinstance(error.value.__cause__, aiohttp.ConnectionTimeoutError)

    @staticmethod
    @pytest.mark.asyncio
    async def test_fails_if_the_server_does_not_take_the_request() -> None:
        async def never_read(_: asyncio.StreamReader, __: asyncio.StreamWriter) -> None:
            await stall()

        server = await asyncio.start_server(never_read, '127.0.0.1', 0)
        port = server.sockets[0].getsockname()[1]

        try:
            async with Client(
                f'http://127.0.0.1:{port}', 'secret', stall_timeout=STALL_TIMEOUT_SECONDS
            ) as client:
                with pytest.raises(TimeoutError) as error:
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
                assert type(error.value) is TimeoutError
        finally:
            server.close()

    @staticmethod
    @pytest.mark.asyncio
    async def test_does_not_count_the_time_a_request_waits_for_a_free_connection(
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class SingleConnectionConnector(aiohttp.TCPConnector):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, limit=1, **kwargs)

        monkeypatch.setattr(aiohttp.client, 'TCPConnector', SingleConnectionConnector)

        request_count = 0

        async def write_stream(response: web.StreamResponse) -> None:
            nonlocal request_count
            request_count += 1

            # The first query keeps the only connection busy, the second one
            # answers with a row as soon as it gets the connection.
            if request_count == 1:
                while True:
                    await response.write(HEARTBEAT_LINE)
                    await asyncio.sleep(STALL_TIMEOUT_SECONDS / 5)
            await response.write(ROW_LINE)

        async with StreamServer(write_stream, stall_timeout=STALL_TIMEOUT_SECONDS) as server:
            client = server.get_client()

            first_query = asyncio.create_task(run_eventql_query(client))
            await asyncio.sleep(STALL_TIMEOUT_SECONDS / 5)
            second_query = asyncio.create_task(run_eventql_query(client))

            await asyncio.sleep(3 * STALL_TIMEOUT_SECONDS)
            assert not second_query.done()

            first_query.cancel()
            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await second_query

            assert request_count == 2
