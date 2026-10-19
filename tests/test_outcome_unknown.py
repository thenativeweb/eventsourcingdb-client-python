import asyncio
import json
import socket
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
    CustomError,
    DbApiError,
    EventCandidate,
    OutcomeUnknownError,
    ServerError,
    is_outcome_unknown,
)
from eventsourcingdb.errors.is_outcome_unknown import (
    OUTCOME_UNKNOWN_ATTRIBUTE,
    OUTCOME_UNKNOWN_NOTE,
)
from eventsourcingdb.http_client import HttpClient
from eventsourcingdb.transport import Transport
from eventsourcingdb.transport.v1 import V1Transport
from eventsourcingdb.transport.v2 import V2Transport

from .event.fixtures import WRITTEN_EVENTS_FROM_V2_API, WRITTEN_EVENTS_WITH_HASH_V2
from .shared.requests import WRITES, Request, run_eventql_query
from .shared.stream_server import Api, StreamServer
from .shared.util.get_random_available_port import get_random_available_port

STALL_TIMEOUT_SECONDS = 0.5
GUARD_TIMEOUT_SECONDS = 5

TEXT_PLAIN = {'Content-Type': 'text/plain; charset=utf-8'}
V2_HEARTBEAT = b'{"type":"heartbeat","data":{}}\n'
V2_END = b'{"type":"end","data":{}}\n'
SUCCESSFUL_WRITES: dict[Api, dict[str, bytes]] = {
    'v1': {
        'write_events': WRITTEN_EVENTS_WITH_HASH_V2.encode('utf-8'),
        'register_event_schema': b'',
    },
    'v2': {
        'write_events': WRITTEN_EVENTS_FROM_V2_API.encode('utf-8'),
        'register_event_schema': (
            b'{"type":"event","data":{"type":"io.eventsourcingdb.api.event-schema-registered"}}\n'
            + V2_END
        ),
    },
}

APIS: list[Api] = ['v1', 'v2']
WRITES_PER_API = [
    pytest.param(api, write.values[0], id=f'{api}, {write.id}') for api in APIS for write in WRITES
]

TransportWrite = Callable[[Transport], Awaitable[Any]]


async def write_events_with(transport: Transport) -> None:
    await transport.write_events(
        [
            EventCandidate(
                source='https://www.eventsourcingdb.io',
                subject='/books/42',
                type='io.eventsourcingdb.library.book-acquired',
                data={},
            )
        ],
        [],
    )


async def register_event_schema_with(transport: Transport) -> None:
    await transport.register_event_schema(
        'io.eventsourcingdb.library.book-acquired', {'type': 'object'}
    )


TRANSPORTS: dict[Api, Callable[[HttpClient], Transport]] = {
    'v1': V1Transport,
    # Without a client that chose it, there is nothing to forget.
    'v2': lambda http_client: V2Transport(http_client, lambda _: None),
}

# Writes through a transport of their own, which never asks the server which
# API it offers, so that the write is the first request to connect.
TRANSPORT_WRITES_PER_API = [
    pytest.param(api, write, id=f'{api}, {name}')
    for api in APIS
    for name, write in [
        ('write_events', write_events_with),
        ('register_event_schema', register_event_schema_with),
    ]
]


def error_item(code: str) -> bytes:
    return json.dumps({
        'type': 'error',
        'data': {
            'code': f'https://docs.eventsourcingdb.io/errors/{code}',
            'description': f'{code} happened',
            'details': {},
        },
    }).encode('utf-8') + b'\n'


def answer_with(content: bytes, *, then_stall: bool = False):
    async def write_stream(response: web.StreamResponse) -> None:
        await response.write(content)
        if then_stall:
            await asyncio.Event().wait()

    return write_stream


async def outcome_of(request_: Request, server: StreamServer) -> BaseException | None:
    async with server:
        try:
            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await request_(server.get_client())
        except (CustomError, aiohttp.ClientError) as error:
            return error

    return None


def assert_is_outcome_unknown(error: BaseException | None, cause: type[BaseException]) -> None:
    assert type(error) is OutcomeUnknownError
    assert isinstance(error.cause, cause)
    assert error.__cause__ is error.cause


class HangingResolver(aiohttp.abc.AbstractResolver):
    def __init__(self, *_: Any, **__: Any) -> None:
        pass

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[aiohttp.abc.ResolveResult]:
        await asyncio.Event().wait()
        return []

    async def close(self) -> None:
        pass


class TestWritesThatWereCertainlyNotStored:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'write'), TRANSPORT_WRITES_PER_API)
    async def test_raises_the_error_if_the_name_of_the_server_cannot_be_resolved(
        api: Api, write: TransportWrite
    ) -> None:
        async with HttpClient('http://eventsourcingdb.invalid', 'secret') as http_client:
            with pytest.raises(aiohttp.ClientConnectorDNSError):
                await write(TRANSPORTS[api](http_client))

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'write'), TRANSPORT_WRITES_PER_API)
    async def test_raises_the_error_if_connecting_fails(api: Api, write: TransportWrite) -> None:
        port = get_random_available_port()

        async with HttpClient(f'http://127.0.0.1:{port}', 'secret') as http_client:
            with pytest.raises(aiohttp.ClientConnectorError) as error:
                await write(TRANSPORTS[api](http_client))

        assert not isinstance(error.value, OutcomeUnknownError)

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'write'), TRANSPORT_WRITES_PER_API)
    async def test_raises_the_error_if_tls_fails(api: Api, write: TransportWrite) -> None:
        async with StreamServer(None) as server:
            https_url = server.base_url.replace('http://', 'https://')

            async with HttpClient(https_url, 'secret') as http_client:
                with pytest.raises(aiohttp.ClientError) as error:
                    await write(TRANSPORTS[api](http_client))

            assert isinstance(error.value, aiohttp.ClientConnectorError | aiohttp.ClientSSLError)
            assert server.requests == []

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'write'), TRANSPORT_WRITES_PER_API)
    async def test_raises_a_stalled_connection_if_connecting_stalls(
        monkeypatch: pytest.MonkeyPatch, api: Api, write: TransportWrite
    ) -> None:
        monkeypatch.setattr(aiohttp.connector, 'DefaultResolver', HangingResolver)

        async with HttpClient(
            'http://eventsourcingdb.test:3000', 'secret', stall_timeout=STALL_TIMEOUT_SECONDS
        ) as http_client:
            with pytest.raises(ConnectionStalledError) as error:
                async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                    await write(TRANSPORTS[api](http_client))

        assert type(error.value) is ConnectionStalledError

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'write'), TRANSPORT_WRITES_PER_API)
    async def test_is_cancelled_if_cancelled_before_it_connects(
        monkeypatch: pytest.MonkeyPatch, api: Api, write: TransportWrite
    ) -> None:
        resolving = asyncio.Event()

        class SignallingHangingResolver(HangingResolver):
            async def resolve(self, *args: Any, **kwargs: Any) -> list[aiohttp.abc.ResolveResult]:
                resolving.set()
                return await super().resolve(*args, **kwargs)

        monkeypatch.setattr(aiohttp.connector, 'DefaultResolver', SignallingHangingResolver)

        async with HttpClient('http://eventsourcingdb.test:3000', 'secret') as http_client:
            task = asyncio.create_task(write(TRANSPORTS[api](http_client)))

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await resolving.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError) as error:
                    await task

        assert task.cancelled()
        assert not is_outcome_unknown(error.value)
        assert not hasattr(error.value, OUTCOME_UNKNOWN_ATTRIBUTE)
        assert OUTCOME_UNKNOWN_NOTE not in getattr(error.value, '__notes__', [])

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'request_'), WRITES_PER_API)
    async def test_raises_a_stalled_connection_if_it_waits_for_a_free_connection_in_vain(
        monkeypatch: pytest.MonkeyPatch, api: Api, request_: Request
    ) -> None:
        class SingleConnectionConnector(aiohttp.TCPConnector):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, limit=1, **kwargs)

        monkeypatch.setattr(aiohttp.client, 'TCPConnector', SingleConnectionConnector)
        heartbeat = b'{"type":"heartbeat","payload":{}}\n' if api == 'v1' else V2_HEARTBEAT

        async def keep_busy(response: web.StreamResponse) -> None:
            while True:
                await response.write(heartbeat)
                await asyncio.sleep(STALL_TIMEOUT_SECONDS / 5)

        async with StreamServer(keep_busy, stall_timeout=STALL_TIMEOUT_SECONDS, api=api) as server:
            client = server.get_client()
            busy_query = asyncio.create_task(run_eventql_query(client))
            try:
                with pytest.raises(ConnectionStalledError) as error:
                    async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                        # Once the busy query has reached the server, the client
                        # knows the API, and the write waits for a connection.
                        await server.request_received.wait()
                        await request_(client)
            finally:
                busy_query.cancel()

        assert type(error.value) is ConnectionStalledError
        assert len(server.requests) == 1

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('request_', [write.values[0] for write in WRITES])
    @pytest.mark.parametrize(
        'code',
        [
            'precondition-violated',
            'event-schema-violated',
            'event-schema-already-registered',
            'events-missing',
            'capacity-exceeded',
            'license-invalid',
            'store-read-only',
            'disk-full',
            'indexes-rebuilding',
            'server-shutting-down',
        ],
    )
    async def test_raises_an_error_item_of_the_v2_api_other_than_store_failed(
        request_: Request, code: str
    ) -> None:
        error = await outcome_of(
            request_, StreamServer(answer_with(V2_HEARTBEAT + error_item(code) + V2_END), api='v2')
        )

        assert type(error) is DbApiError
        assert error.code == f'https://docs.eventsourcingdb.io/errors/{code}'

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'request_'), WRITES_PER_API)
    @pytest.mark.parametrize('status', [400, 401, 408, 413, 429, 503])
    async def test_raises_an_error_of_a_status_that_refuses_the_request(
        api: Api, request_: Request, status: int
    ) -> None:
        error = await outcome_of(
            request_,
            StreamServer(answer_with(b'refused'), status=status, headers=TEXT_PLAIN, api=api),
        )

        assert type(error) is DbApiError
        assert error.status == status

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('request_', [write.values[0] for write in WRITES])
    @pytest.mark.parametrize('status', [403, 404, 405, 409, 422, 507])
    async def test_raises_an_error_of_another_4xx_or_507_of_the_v1_api(
        request_: Request, status: int
    ) -> None:
        error = await outcome_of(
            request_,
            StreamServer(answer_with(b'refused'), status=status, headers=TEXT_PLAIN, api='v1'),
        )

        assert type(error) is DbApiError
        assert error.status == status


class TestWritesWhoseOutcomeIsUnknown:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('request_', [write.values[0] for write in WRITES])
    async def test_reports_an_unknown_outcome_for_a_store_that_failed(request_: Request) -> None:
        error = await outcome_of(
            request_,
            StreamServer(answer_with(error_item('store-failed') + V2_END), api='v2'),
        )

        assert_is_outcome_unknown(error, DbApiError)
        assert error.cause.code == 'https://docs.eventsourcingdb.io/errors/store-failed'  # type: ignore[union-attr]

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'request_'), WRITES_PER_API)
    @pytest.mark.parametrize('status', [500, 502, 504])
    async def test_reports_an_unknown_outcome_for_a_server_error(
        api: Api, request_: Request, status: int
    ) -> None:
        error = await outcome_of(
            request_,
            StreamServer(answer_with(b'failed'), status=status, headers=TEXT_PLAIN, api=api),
        )

        assert_is_outcome_unknown(error, DbApiError)
        assert error.cause.status == status  # type: ignore[union-attr]

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('request_', [write.values[0] for write in WRITES])
    @pytest.mark.parametrize('status', [404, 405, 409, 507])
    async def test_reports_an_unknown_outcome_for_another_status_of_the_v2_api(
        request_: Request, status: int
    ) -> None:
        error = await outcome_of(
            request_,
            StreamServer(answer_with(b'failed'), status=status, headers=TEXT_PLAIN, api='v2'),
        )

        assert_is_outcome_unknown(error, DbApiError)

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'request_'), WRITES_PER_API)
    @pytest.mark.parametrize('status', [200, 400, 503])
    async def test_reports_an_unknown_outcome_for_an_answer_that_is_not_from_eventsourcingdb(
        api: Api, request_: Request, status: int
    ) -> None:
        name = 'write_events' if request_.__name__ == 'write_events' else 'register_event_schema'
        error = await outcome_of(
            request_,
            StreamServer(
                answer_with(SUCCESSFUL_WRITES[api][name]),
                status=status,
                headers={'Server': 'nginx'},
                api=api,
            ),
        )

        assert_is_outcome_unknown(error, ServerError)
        assert 'Server must be EventSourcingDB' in str(error.cause)  # type: ignore[union-attr]

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'request_'), WRITES_PER_API)
    async def test_reports_an_unknown_outcome_if_the_server_stalls_before_answering(
        api: Api, request_: Request
    ) -> None:
        error = await outcome_of(
            request_, StreamServer(None, stall_timeout=STALL_TIMEOUT_SECONDS, api=api)
        )

        assert_is_outcome_unknown(error, ConnectionStalledError)

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('request_', [write.values[0] for write in WRITES])
    async def test_reports_an_unknown_outcome_if_the_server_stalls_after_a_heartbeat(
        request_: Request,
    ) -> None:
        error = await outcome_of(
            request_,
            StreamServer(
                answer_with(V2_HEARTBEAT, then_stall=True),
                stall_timeout=STALL_TIMEOUT_SECONDS,
                api='v2',
            ),
        )

        assert_is_outcome_unknown(error, ConnectionStalledError)

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('request_', [write.values[0] for write in WRITES])
    async def test_reports_an_unknown_outcome_if_the_stream_ends_without_its_end_item(
        request_: Request,
    ) -> None:
        name = 'write_events' if request_.__name__ == 'write_events' else 'register_event_schema'
        answer = SUCCESSFUL_WRITES['v2'][name].replace(V2_END, b'')

        error = await outcome_of(request_, StreamServer(answer_with(V2_HEARTBEAT + answer), api='v2'))

        assert_is_outcome_unknown(error, ServerError)
        assert 'closed the stream before it ended' in str(error.cause)  # type: ignore[union-attr]

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ('api', 'request_', 'answer'),
        [
            pytest.param('v1', WRITES[0].values[0], b'[{"broken', id='v1, write_events'),
            pytest.param('v2', WRITES[0].values[0], b'{"broken\n', id='v2, write_events'),
            pytest.param('v2', WRITES[1].values[0], b'{"broken\n', id='v2, register_event_schema'),
        ],
    )
    async def test_reports_an_unknown_outcome_for_an_answer_that_cannot_be_parsed(
        api: Api, request_: Request, answer: bytes
    ) -> None:
        error = await outcome_of(request_, StreamServer(answer_with(answer), api=api))

        assert type(error) is OutcomeUnknownError

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'request_'), WRITES_PER_API)
    async def test_reports_an_unknown_outcome_if_the_connection_breaks_after_connecting(
        api: Api, request_: Request
    ) -> None:
        # Answers the ping that the client asks with which API the server
        # offers, and closes every later connection once it has the request.
        async def answer_ping_then_break(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            head = await reader.readuntil(b'\r\n\r\n')
            if head.startswith(b'GET /api/v2/system/ping'):
                body = (
                    b'{"type":"event","data":{"type":"io.eventsourcingdb.api.ping-received"}}'
                    if api == 'v2'
                    else b'404 page not found'
                )
                status = b'200 OK' if api == 'v2' else b'404 Not Found'
                writer.write(
                    b'HTTP/1.1 ' + status + b'\r\nServer: EventSourcingDB/test\r\n'
                    b'Connection: close\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n'
                    + body
                )
                await writer.drain()
            writer.close()

        server = await asyncio.start_server(answer_ping_then_break, '127.0.0.1', 0)
        port = server.sockets[0].getsockname()[1]
        try:
            async with Client(f'http://127.0.0.1:{port}', 'secret') as client:
                with pytest.raises(OutcomeUnknownError) as error:
                    async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                        await request_(client)
        finally:
            server.close()

        assert isinstance(error.value.cause, aiohttp.ClientError)

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'request_'), WRITES_PER_API)
    async def test_returns_normally_if_the_write_succeeds(api: Api, request_: Request) -> None:
        name = 'write_events' if request_.__name__ == 'write_events' else 'register_event_schema'

        error = await outcome_of(
            request_, StreamServer(answer_with(SUCCESSFUL_WRITES[api][name]), api=api)
        )

        assert error is None


def assert_marked(cancellation: BaseException) -> None:
    assert type(cancellation) is asyncio.CancelledError
    assert getattr(cancellation, OUTCOME_UNKNOWN_ATTRIBUTE) is True
    assert OUTCOME_UNKNOWN_NOTE in cancellation.__notes__


class TestWritesThatAreCancelledOnceTheyHaveAConnection:
    # A cancelled write is marked rather than wrapped, so that it cancels as
    # asyncio expects, while is_outcome_unknown tells that it may have been
    # stored.
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'request_'), WRITES_PER_API)
    async def test_cancels_the_task_and_marks_the_cancellation(
        api: Api, request_: Request
    ) -> None:
        async with StreamServer(None, api=api) as server:
            task = asyncio.create_task(request_(server.get_client()))

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await server.request_received.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError) as error:
                    await task

        assert task.cancelled()
        assert_marked(error.value)
        assert is_outcome_unknown(error.value)

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'request_'), WRITES_PER_API)
    async def test_raises_the_timeout_error_of_asyncio_timeout_whose_is_outcome_unknown(
        api: Api, request_: Request
    ) -> None:
        async with StreamServer(None, api=api) as server:
            with pytest.raises(TimeoutError) as error:
                async with asyncio.timeout(GUARD_TIMEOUT_SECONDS) as deadline:
                    # The deadline of the caller passes once the server has
                    # the request.
                    async def end_deadline_once_received() -> None:
                        await server.request_received.wait()
                        deadline.reschedule(asyncio.get_running_loop().time())

                    ending_deadline = asyncio.create_task(end_deadline_once_received())
                    await request_(server.get_client())

            await ending_deadline

        assert deadline.expired()
        assert type(error.value) is TimeoutError
        assert_marked(error.value.__cause__)  # type: ignore[arg-type]
        assert is_outcome_unknown(error.value)

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'request_'), WRITES_PER_API)
    async def test_raises_the_timeout_error_of_wait_for_whose_is_outcome_unknown(
        api: Api, request_: Request
    ) -> None:
        async with StreamServer(None, api=api) as server:
            with pytest.raises(TimeoutError) as error:
                await asyncio.wait_for(request_(server.get_client()), STALL_TIMEOUT_SECONDS)

            # The server never answers, so the deadline passed after the
            # request reached it.
            assert server.request_received.is_set()

        assert type(error.value) is TimeoutError
        assert is_outcome_unknown(error.value)

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'request_'), WRITES_PER_API)
    async def test_is_cancelled_like_any_task_of_a_task_group_whose_sibling_fails(
        api: Api, request_: Request
    ) -> None:
        async with StreamServer(None, api=api) as server:

            async def fail_once_the_write_was_sent() -> None:
                await server.request_received.wait()
                raise ValueError('The sibling failed.')

            handled: list[BaseException] = []
            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                try:
                    async with asyncio.TaskGroup() as task_group:
                        task_group.create_task(request_(server.get_client()))
                        task_group.create_task(fail_once_the_write_was_sent())
                except* ValueError as group:
                    handled.extend(group.exceptions)

        assert [str(error) for error in handled] == ['The sibling failed.']

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'request_'), WRITES_PER_API)
    async def test_cancels_a_loop_that_retries_writes_whose_is_outcome_unknown(
        api: Api, request_: Request
    ) -> None:
        attempts = 0

        async with StreamServer(None, stall_timeout=STALL_TIMEOUT_SECONDS, api=api) as server:

            async def retry_until_known() -> None:
                # A few attempts, so that a cancellation that this loop
                # swallowed lets the task end rather than hang.
                nonlocal attempts
                for _ in range(3):
                    attempts += 1
                    try:
                        await request_(server.get_client())
                        return
                    except OutcomeUnknownError:
                        continue

            task = asyncio.create_task(retry_until_known())

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await server.request_received.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task

        assert task.cancelled()
        assert attempts == 1


class TestIsOutcomeUnknown:
    @staticmethod
    def test_is_true_for_an_outcome_unknown_error_and_errors_caused_by_one() -> None:
        outcome_unknown_error = OutcomeUnknownError(ConnectionStalledError(30))

        try:
            try:
                raise outcome_unknown_error
            except OutcomeUnknownError as error:
                raise RuntimeError('Failed to save.') from error
        except RuntimeError as error:
            caused = error

        assert is_outcome_unknown(outcome_unknown_error)
        assert is_outcome_unknown(caused)

    @staticmethod
    def test_is_false_for_an_error_raised_while_handling_one_without_being_caused_by_it() -> None:
        # Such an error tells nothing about whether the write was stored,
        # whether its context is suppressed or not.
        def raise_while_handling(suppress_context: bool) -> BaseException:
            try:
                try:
                    raise OutcomeUnknownError(ConnectionStalledError(30))
                except OutcomeUnknownError:
                    if suppress_context:
                        raise ValueError('The input is invalid.') from None
                    raise ValueError('The input is invalid.')
            except ValueError as error:
                return error

        unrelated = raise_while_handling(suppress_context=False)
        suppressed = raise_while_handling(suppress_context=True)

        assert isinstance(unrelated.__context__, OutcomeUnknownError)
        assert isinstance(suppressed.__context__, OutcomeUnknownError)
        assert not is_outcome_unknown(unrelated)
        assert not is_outcome_unknown(suppressed)

    @staticmethod
    def test_is_false_for_other_errors_and_unmarked_cancellations() -> None:
        circular = RuntimeError('One.')
        other = RuntimeError('Two.')
        circular.__cause__ = other
        other.__cause__ = circular

        assert not is_outcome_unknown(asyncio.CancelledError())
        assert not is_outcome_unknown(TimeoutError())
        assert not is_outcome_unknown(ConnectionStalledError(30))
        assert not is_outcome_unknown(circular)


class TestOutcomeUnknownError:
    @staticmethod
    def test_names_its_cause() -> None:
        cause = ConnectionStalledError(30)
        error = OutcomeUnknownError(cause)

        assert error.cause is cause
        assert str(error) == (
            'The write may have been stored, its outcome is unknown: ConnectionStalledError: '
            'Server error occurred: Nothing arrived from the server for 30 seconds'
        )
        assert str(OutcomeUnknownError(asyncio.CancelledError())) == (
            'The write may have been stored, its outcome is unknown: CancelledError'
        )
