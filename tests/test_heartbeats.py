import asyncio
import json
import time
from collections.abc import AsyncGenerator, Callable
from typing import Any

import pytest
from aiohttp import web

from eventsourcingdb import (
    Client,
    ConnectionStalledError,
    ObserveEventsOptions,
)
from eventsourcingdb.http_client import Response

from .shared.stream_server import Api, StreamServer

SHORT_STALL_TIMEOUT_SECONDS = 0.5
GUARD_TIMEOUT_SECONDS = 5

EVENT = {
    'specversion': '1.0',
    'id': '0',
    'time': '2026-10-03T12:00:00.000000000Z',
    'source': 'https://www.eventsourcingdb.io',
    'subject': '/books/42',
    'type': 'io.eventsourcingdb.library.book-acquired',
    'datacontenttype': 'application/json',
    'data': {'title': 'Dune'},
    'predecessorhash': '0' * 64,
    'hash': '1' * 64,
    'traceparent': None,
    'tracestate': None,
    'signature': None,
}
APIS: list[Api] = ['v1', 'v2']
HEARTBEAT_LINES: dict[Api, bytes] = {
    'v1': b'{"type":"heartbeat","payload":{}}\n',
    'v2': b'{"type":"heartbeat","data":{}}\n',
}
ITEM_LINES: dict[Api, dict[str, bytes]] = {
    'v1': {
        'observe_events': json.dumps({'type': 'event', 'payload': EVENT}).encode('utf-8') + b'\n',
        'run_eventql_query': b'{"type":"row","payload":{"title":"Dune"}}\n',
    },
    'v2': {
        'observe_events': json.dumps({'type': 'event', 'data': EVENT}).encode('utf-8') + b'\n',
        'run_eventql_query': b'{"type":"row","data":{"value":{"title":"Dune"}}}\n',
    },
}

StartStream = Callable[[Client], AsyncGenerator[Any]]


def observe_events(client: Client) -> AsyncGenerator[Any]:
    return client.observe_events('/', ObserveEventsOptions(recursive=True))


def run_eventql_query(client: Client) -> AsyncGenerator[Any]:
    return client.run_eventql_query('FROM e IN events PROJECT INTO e')


START_STREAMS = {'observe_events': observe_events, 'run_eventql_query': run_eventql_query}
STREAMS = [
    pytest.param(api, start_stream, id=f'{api}, {name}')
    for api in APIS
    for name, start_stream in START_STREAMS.items()
]
STREAMS_WITH_ITEMS = [
    pytest.param(api, start_stream, ITEM_LINES[api][name], id=f'{api}, {name}')
    for api in APIS
    for name, start_stream in START_STREAMS.items()
]


async def stall() -> None:
    await asyncio.Event().wait()


def stream_server(write_stream: Callable[[web.StreamResponse], Any], api: Api) -> StreamServer:
    return StreamServer(write_stream, stall_timeout=SHORT_STALL_TIMEOUT_SECONDS, api=api)


class TestHeartbeats:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'start_stream'), STREAMS)
    async def test_ends_stream_with_error_if_neither_event_nor_heartbeat_arrives(
        api: Api,
        start_stream: StartStream,
    ) -> None:
        async def write_stream(response: web.StreamResponse) -> None:
            await response.write(HEARTBEAT_LINES[api])
            await stall()

        async with stream_server(write_stream, api) as server:
            started_at = time.monotonic()

            with pytest.raises(
                ConnectionStalledError,
                match='Nothing arrived from the server for 0.5 seconds',
            ) as error:
                async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                    async for _ in start_stream(server.get_client()):
                        pass

            elapsed_seconds = time.monotonic() - started_at
            assert elapsed_seconds >= SHORT_STALL_TIMEOUT_SECONDS
            assert elapsed_seconds < SHORT_STALL_TIMEOUT_SECONDS + 1
            assert type(error.value) is ConnectionStalledError

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await server.client_disconnected.wait()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'start_stream', 'item_line'), STREAMS_WITH_ITEMS)
    async def test_keeps_stream_open_while_heartbeats_arrive(
        api: Api, start_stream: StartStream, item_line: bytes
    ) -> None:
        heartbeat_interval_seconds = 0.1
        heartbeat_count = 15

        async def write_stream(response: web.StreamResponse) -> None:
            for _ in range(heartbeat_count):
                await response.write(HEARTBEAT_LINES[api])
                await asyncio.sleep(heartbeat_interval_seconds)
            await response.write(item_line)
            await stall()

        async with stream_server(write_stream, api) as server:
            started_at = time.monotonic()
            items = []

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                async for item in start_stream(server.get_client()):
                    items.append(item)
                    break

            elapsed_seconds = time.monotonic() - started_at
            assert len(items) == 1
            assert elapsed_seconds > SHORT_STALL_TIMEOUT_SECONDS

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'start_stream', 'item_line'), STREAMS_WITH_ITEMS)
    async def test_delivers_items_that_arrive_within_the_timeout(
        api: Api, start_stream: StartStream, item_line: bytes
    ) -> None:
        item_interval_seconds = 0.2
        item_count = 4

        async def write_stream(response: web.StreamResponse) -> None:
            for _ in range(item_count):
                await response.write(item_line)
                await asyncio.sleep(item_interval_seconds)
            await stall()

        async with stream_server(write_stream, api) as server:
            items = []

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                async for item in start_stream(server.get_client()):
                    items.append(item)
                    if len(items) == item_count:
                        break

            assert len(items) == item_count

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'start_stream'), STREAMS)
    async def test_cancelling_ends_stream_without_a_stalled_connection(
        api: Api,
        start_stream: StartStream,
    ) -> None:
        async def write_stream(response: web.StreamResponse) -> None:
            await response.write(HEARTBEAT_LINES[api])
            await stall()

        async with stream_server(write_stream, api) as server:
            async def consume_stream() -> None:
                async for _ in start_stream(server.get_client()):
                    pass

            task = asyncio.create_task(consume_stream())
            await asyncio.sleep(SHORT_STALL_TIMEOUT_SECONDS / 2)
            task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await task

            assert task.cancelled(), "Task should be marked as cancelled"

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'start_stream'), STREAMS)
    async def test_does_not_report_timeout_of_caller_as_a_stalled_connection(
        api: Api,
        start_stream: StartStream,
    ) -> None:
        async def write_stream(response: web.StreamResponse) -> None:
            await response.write(HEARTBEAT_LINES[api])
            await stall()

        async with stream_server(write_stream, api) as server:
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(SHORT_STALL_TIMEOUT_SECONDS / 2):
                    async for _ in start_stream(server.get_client()):
                        pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_passes_on_timeouts_that_are_not_stalls() -> None:
        class TimingOutStream:
            @staticmethod
            async def readany() -> bytes:
                raise TimeoutError('Session timed out')

        class TimingOutResponse:
            content = TimingOutStream()

            @staticmethod
            def close() -> None:
                pass

        response = Response(TimingOutResponse(), SHORT_STALL_TIMEOUT_SECONDS)  # type: ignore

        with pytest.raises(TimeoutError, match='Session timed out') as error:
            async for _ in response.read_lines():
                pass

        assert type(error.value) is TimeoutError

    @staticmethod
    def test_names_the_stall_timeout_in_the_message() -> None:
        assert str(ConnectionStalledError(30)) == (
            'Server error occurred: Nothing arrived from the server for 30 seconds'
        )
