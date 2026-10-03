import asyncio
import json
import time
from collections.abc import AsyncGenerator, Callable
from typing import Any

import pytest
from aiohttp import web

import eventsourcingdb.read_lines_with_heartbeat_timeout as heartbeat_timeout_module
from eventsourcingdb import Client, HeartbeatTimeoutError, ObserveEventsOptions
from eventsourcingdb.read_lines_with_heartbeat_timeout import (
    read_lines_with_heartbeat_timeout,
)

from .shared.stream_server import StreamServer

SHORT_HEARTBEAT_TIMEOUT_SECONDS = 0.5
GUARD_TIMEOUT_SECONDS = 5

HEARTBEAT_LINE = b'{"type":"heartbeat","payload":{}}\n'
EVENT_LINE = json.dumps({
    'type': 'event',
    'payload': {
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
    },
}).encode('utf-8') + b'\n'
ROW_LINE = b'{"type":"row","payload":{"title":"Dune"}}\n'

StartStream = Callable[[Client], AsyncGenerator[Any]]


def observe_events(client: Client) -> AsyncGenerator[Any]:
    return client.observe_events('/', ObserveEventsOptions(recursive=True))


def run_eventql_query(client: Client) -> AsyncGenerator[Any]:
    return client.run_eventql_query('FROM e IN events PROJECT INTO e')


STREAMS = [
    pytest.param(observe_events, id='observe_events'),
    pytest.param(run_eventql_query, id='run_eventql_query'),
]
STREAMS_WITH_ITEMS = [
    pytest.param(observe_events, EVENT_LINE, id='observe_events'),
    pytest.param(run_eventql_query, ROW_LINE, id='run_eventql_query'),
]


async def stall() -> None:
    await asyncio.Event().wait()


@pytest.fixture
def short_heartbeat_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        heartbeat_timeout_module,
        'HEARTBEAT_TIMEOUT_SECONDS',
        SHORT_HEARTBEAT_TIMEOUT_SECONDS,
    )


@pytest.mark.usefixtures('short_heartbeat_timeout')
class TestHeartbeatTimeout:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('start_stream', STREAMS)
    async def test_ends_stream_with_error_if_neither_event_nor_heartbeat_arrives(
        start_stream: StartStream,
    ) -> None:
        async def write_stream(response: web.StreamResponse) -> None:
            await response.write(HEARTBEAT_LINE)
            await stall()

        async with StreamServer(write_stream) as server:
            started_at = time.monotonic()

            with pytest.raises(
                HeartbeatTimeoutError,
                match='No event and no heartbeat arrived for 30 seconds',
            ):
                async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                    async for _ in start_stream(server.get_client()):
                        pass

            elapsed_seconds = time.monotonic() - started_at
            assert elapsed_seconds >= SHORT_HEARTBEAT_TIMEOUT_SECONDS
            assert elapsed_seconds < SHORT_HEARTBEAT_TIMEOUT_SECONDS + 1

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await server.client_disconnected.wait()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('start_stream', 'item_line'), STREAMS_WITH_ITEMS)
    async def test_keeps_stream_open_while_heartbeats_arrive(
        start_stream: StartStream, item_line: bytes
    ) -> None:
        heartbeat_interval_seconds = 0.1
        heartbeat_count = 15

        async def write_stream(response: web.StreamResponse) -> None:
            for _ in range(heartbeat_count):
                await response.write(HEARTBEAT_LINE)
                await asyncio.sleep(heartbeat_interval_seconds)
            await response.write(item_line)
            await stall()

        async with StreamServer(write_stream) as server:
            started_at = time.monotonic()
            items = []

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                async for item in start_stream(server.get_client()):
                    items.append(item)
                    break

            elapsed_seconds = time.monotonic() - started_at
            assert len(items) == 1
            assert elapsed_seconds > SHORT_HEARTBEAT_TIMEOUT_SECONDS

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('start_stream', 'item_line'), STREAMS_WITH_ITEMS)
    async def test_delivers_items_that_arrive_within_the_timeout(
        start_stream: StartStream, item_line: bytes
    ) -> None:
        item_interval_seconds = 0.2
        item_count = 4

        async def write_stream(response: web.StreamResponse) -> None:
            for _ in range(item_count):
                await response.write(item_line)
                await asyncio.sleep(item_interval_seconds)

        async with StreamServer(write_stream) as server:
            items = []

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                async for item in start_stream(server.get_client()):
                    items.append(item)

            assert len(items) == item_count

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('start_stream', STREAMS)
    async def test_cancelling_ends_stream_without_heartbeat_timeout(
        start_stream: StartStream,
    ) -> None:
        async def write_stream(response: web.StreamResponse) -> None:
            await response.write(HEARTBEAT_LINE)
            await stall()

        async with StreamServer(write_stream) as server:
            async def consume_stream() -> None:
                async for _ in start_stream(server.get_client()):
                    pass

            task = asyncio.create_task(consume_stream())
            await asyncio.sleep(SHORT_HEARTBEAT_TIMEOUT_SECONDS / 2)
            task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await task

            assert task.cancelled(), "Task should be marked as cancelled"

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('start_stream', STREAMS)
    async def test_does_not_report_timeout_of_caller_as_heartbeat_timeout(
        start_stream: StartStream,
    ) -> None:
        async def write_stream(response: web.StreamResponse) -> None:
            await response.write(HEARTBEAT_LINE)
            await stall()

        async with StreamServer(write_stream) as server:
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(SHORT_HEARTBEAT_TIMEOUT_SECONDS / 2):
                    async for _ in start_stream(server.get_client()):
                        pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_passes_on_timeouts_that_are_not_heartbeat_timeouts() -> None:
        class TimingOutStream:
            @staticmethod
            async def readline() -> bytes:
                raise TimeoutError('Session timed out')

        with pytest.raises(TimeoutError, match='Session timed out'):
            async for _ in read_lines_with_heartbeat_timeout(TimingOutStream()):  # type: ignore
                pass
