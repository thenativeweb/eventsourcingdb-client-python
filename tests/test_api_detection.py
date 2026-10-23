import asyncio
import json
import logging
from collections.abc import Mapping

import aiohttp
import pytest
from aiohttp import web

from eventsourcingdb import (
    Client,
    ConnectionStalledError,
    CustomError,
    DbApiError,
    ErrorCode,
    EventCandidate,
    IncompatibleServerError,
    IsSubjectPristine,
    OutcomeUnknownError,
    Precondition,
    PreconditionOptions,
    ReadEventsOptions,
    ReadSubjectsOptions,
    ServerError,
)

from .event.fixtures import WRITTEN_EVENTS_FROM_V2_API, WRITTEN_EVENTS_WITH_HASH_V2
from .shared.database import Database
from .shared.requests import ALL_REQUESTS, WRITES, Request, read_event_type, read_events
from .shared.stream_server import (
    SERVER_HEADER,
    Answer,
    StreamServer,
    answer_probe_with_v2_api,
    answer_probe_without_v2_api,
)
from .shared.util.get_random_available_port import get_random_available_port

GUARD_TIMEOUT_SECONDS = 5

# The ping of the v2 API is the ping that the client asks with whether the
# server offers the v2 API, and a write reports an unknown outcome instead.
REQUESTS_EXCEPT_PING_AND_WRITES = [
    parameter
    for parameter in ALL_REQUESTS
    if parameter.id != 'ping' and parameter.id not in {write.id for write in WRITES}
]
REQUESTS_EXCEPT_PING = [parameter for parameter in ALL_REQUESTS if parameter.id != 'ping']

TEXTS_WITHOUT_V2_API = {404: '404 page not found\n', 405: 'Method Not Allowed\n'}
PROXY_HEADER = {'Server': 'nginx'}
# Who answers a path of the v2 API with 404 or 405, and the error with which
# the request fails, as it did before the client forgot the API.
ANSWERED_BY = [
    pytest.param(SERVER_HEADER, DbApiError, id='EventSourcingDB'),
    pytest.param(PROXY_HEADER, ServerError, id='a proxy'),
]
EVENT_TYPE_UNKNOWN_ITEM = json.dumps({
    'type': 'error',
    'data': {
        'code': ErrorCode.EVENT_TYPE_UNKNOWN,
        'description': 'event type unknown',
        'details': {},
    },
}) + '\n'


def answer_probe_with_status(status: int, text: str = 'nope'):
    async def answer_probe(_: web.Request) -> web.StreamResponse:
        return web.Response(status=status, text=text, headers=SERVER_HEADER)

    return answer_probe


def answer_probes_in_turn(*answers):
    remaining = list(answers)

    async def answer_probe(request: web.Request) -> web.StreamResponse:
        return await remaining.pop(0)(request)

    return answer_probe


async def read_all_events(server: StreamServer) -> None:
    async for _ in server.get_client().read_events('/', ReadEventsOptions(recursive=True)):
        pass


def v2_stream_server(**options: object) -> StreamServer:
    async def write_stream(response: web.StreamResponse) -> None:
        await response.write(b'{"type":"end","data":{}}\n')

    return StreamServer(write_stream, api='v2', **options)  # type: ignore[arg-type]


def is_v2_path(request: web.Request) -> bool:
    return request.path.startswith('/api/v2/')


def apis_of(server: StreamServer) -> list[str]:
    # The version of the API that each request went through, such as v2.
    return [request.path.split('/')[2] for request in server.requests]


async def answer_read_events(request: web.Request) -> web.StreamResponse:
    # Reading events finds none, through either API.
    return web.Response(
        text='{"type":"end","data":{}}\n' if is_v2_path(request) else '', headers=SERVER_HEADER
    )


async def answer_writes_and_read_events(request: web.Request) -> web.StreamResponse:
    # Writing events stores two, and reading events finds none, through either
    # API.
    if request.path == '/api/v2/data/write-events':
        return web.Response(text=WRITTEN_EVENTS_FROM_V2_API, headers=SERVER_HEADER)
    if request.path == '/api/v1/write-events':
        return web.Response(text=WRITTEN_EVENTS_WITH_HASH_V2, headers=SERVER_HEADER)
    return await answer_read_events(request)


async def write_events_with(client: Client, precondition: Precondition) -> None:
    await client.write_events(
        [
            EventCandidate(
                source='https://www.eventsourcingdb.io',
                subject='/books/42',
                type='io.eventsourcingdb.library.book-acquired',
                data={},
            )
        ],
        [precondition],
    )


def answer_without_v2_api(
    status: int = 404, headers: Mapping[str, str] = SERVER_HEADER
) -> web.StreamResponse:
    # As EventSourcingDB 1.2 answers a path of the v2 API, or, with headers of
    # its own, a proxy that only forwards the v1 API.
    return web.Response(status=status, text=TEXTS_WITHOUT_V2_API[status], headers=headers)


class Rollback:
    """
    Answers as a server that offers the v2 API, until the test rolls it back
    to a version without it. From then on, it answers the ping and every other
    path of the v2 API with the given status and headers. Every other request
    it answers with its answer function, which reads events unless the test
    replaces it.
    """

    def __init__(self, status: int = 404, headers: Mapping[str, str] = SERVER_HEADER) -> None:
        self.is_rolled_back = False
        self.answer: Answer = answer_read_events
        self.__status = status
        self.__headers = headers

    def create_server(self) -> StreamServer:
        return StreamServer(None, answer_probe=self.__answer_probe, answer=self.__answer)

    async def __answer_probe(self, request: web.Request) -> web.StreamResponse:
        if self.is_rolled_back:
            return answer_without_v2_api(self.__status, self.__headers)
        return await answer_probe_with_v2_api(request)

    async def __answer(self, request: web.Request) -> web.StreamResponse:
        if self.is_rolled_back and is_v2_path(request):
            return answer_without_v2_api(self.__status, self.__headers)
        return await self.answer(request)


class HeldRequests:
    """
    Holds every request of the v2 API while it is holding, until the test
    releases it, and then answers it with 404, as a server without the v2
    API. Every other request reads events.
    """

    def __init__(self) -> None:
        self.is_holding = False
        self.__releases: asyncio.Queue[asyncio.Future[None]] = asyncio.Queue()

    async def answer(self, request: web.Request) -> web.StreamResponse:
        if not self.is_holding or not is_v2_path(request):
            return await answer_read_events(request)

        release = asyncio.get_running_loop().create_future()
        self.__releases.put_nowait(release)
        await release
        return answer_without_v2_api()

    async def send(self, client: Client) -> tuple[asyncio.Task[None], asyncio.Future[None]]:
        # Reads events, and returns once the request arrived, so that the test
        # knows which request it releases.
        request_ = asyncio.create_task(read_events(client))
        return request_, await self.__releases.get()


class TestApiDetection:
    @staticmethod
    @pytest.mark.asyncio
    async def test_sends_no_request_when_the_client_is_created() -> None:
        async with v2_stream_server() as server:
            client = server.create_client()
            await client.__aexit__()

            assert server.probe_count == 0
            assert server.requests == []

    @staticmethod
    @pytest.mark.asyncio
    async def test_speaks_the_v2_api_if_the_server_answers_its_ping() -> None:
        async with v2_stream_server() as server:
            await read_all_events(server)
            await read_all_events(server)

            assert server.probe_count == 1
            assert [(request.method, request.path) for request in server.requests] == [
                ('QUERY', '/api/v2/data/read-events'),
                ('QUERY', '/api/v2/data/read-events'),
            ]

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('status', [404, 405])
    async def test_speaks_the_v1_api_if_the_server_does_not_know_the_ping_of_the_v2_api(
        status: int,
    ) -> None:
        async def write_stream(_: web.StreamResponse) -> None:
            pass

        async with StreamServer(
            write_stream, answer_probe=answer_probe_with_status(status, '404 page not found\n')
        ) as server:
            await read_all_events(server)
            await read_all_events(server)

            assert server.probe_count == 1
            assert [(request.method, request.path) for request in server.requests] == [
                ('POST', '/api/v1/read-events'),
                ('POST', '/api/v1/read-events'),
            ]

    @staticmethod
    @pytest.mark.asyncio
    async def test_asks_each_client_on_its_own() -> None:
        async with v2_stream_server() as server:
            await read_all_events(server)

            async with server.create_client() as other_client:
                async for _ in other_client.read_events('/', ReadEventsOptions(recursive=True)):
                    pass

            assert server.probe_count == 2

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ('answer_probe', 'expected_error'),
        [
            pytest.param(answer_probe_with_status(500, 'internal server error'), DbApiError, id='500'),
            pytest.param(answer_probe_with_status(503, 'shutting down'), DbApiError, id='503'),
            pytest.param(answer_probe_with_status(401, 'unauthorized'), DbApiError, id='401'),
            pytest.param(
                answer_probe_with_status(200, '<html>management UI</html>'),
                ServerError,
                id='200 that is not a v2 envelope',
            ),
            pytest.param(
                answer_probe_with_status(200, '{"type":"event","data":{"type":"something.else"}}'),
                ServerError,
                id='200 with another event',
            ),
        ],
    )
    async def test_fails_with_the_error_of_an_inconclusive_ping_and_asks_again_next_time(
        answer_probe, expected_error: type[Exception]
    ) -> None:
        async with v2_stream_server(
            answer_probe=answer_probes_in_turn(answer_probe, answer_probe_with_v2_api)
        ) as server:
            with pytest.raises(expected_error) as error:
                await read_all_events(server)

            assert type(error.value) is expected_error
            assert server.requests == []

            await read_all_events(server)

            assert server.probe_count == 2
            assert [request.path for request in server.requests] == ['/api/v2/data/read-events']

    @staticmethod
    @pytest.mark.asyncio
    async def test_reports_the_status_and_text_of_a_failed_ping() -> None:
        async with v2_stream_server(
            answer_probe=answer_probe_with_status(500, 'internal server error\n')
        ) as server:
            with pytest.raises(DbApiError) as error:
                await read_all_events(server)

        assert (error.value.status, error.value.description, error.value.code) == (
            500,
            'internal server error',
            None,
        )

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('status', [404, 405])
    @pytest.mark.parametrize(
        ('content_type', 'body'),
        [
            pytest.param('text/plain', 'not found', id='text'),
            pytest.param(
                'text/html',
                '<html><head><title>404 Not Found</title></head><body><center>'
                '<h1>404 Not Found</h1></center><hr><center>nginx</center></body></html>',
                id='html',
            ),
            pytest.param(None, '', id='empty'),
        ],
    )
    async def test_speaks_the_v1_api_if_a_proxy_that_only_forwards_it_answers_the_ping(
        status: int, content_type: str | None, body: str
    ) -> None:
        async def answer_probe_as_proxy(_: web.Request) -> web.StreamResponse:
            return web.Response(
                status=status,
                text=body if content_type else None,
                content_type=content_type,
                headers={'Server': 'nginx'},
            )

        async def write_stream(response: web.StreamResponse) -> None:
            await response.write(b'{"type":"subject","payload":{"subject":"/"}}\n')

        async with StreamServer(write_stream, answer_probe=answer_probe_as_proxy) as server:
            subjects = [
                subject
                async for subject in server.get_client().read_subjects(
                    '/', ReadSubjectsOptions(recursive=True)
                )
            ]

            assert subjects == ['/']
            assert server.probe_count == 1
            assert [request.path for request in server.requests] == ['/api/v1/read-subjects']

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('status', [200, 500])
    async def test_fails_if_another_answer_to_the_ping_is_not_from_eventsourcingdb(
        status: int,
    ) -> None:
        async def answer_probe(request: web.Request) -> web.StreamResponse:
            response = await answer_probe_with_v2_api(request)
            response.set_status(status)
            del response.headers['Server']
            return response

        async with v2_stream_server(
            answer_probe=answer_probes_in_turn(answer_probe, answer_probe_with_v2_api)
        ) as server:
            with pytest.raises(ServerError, match='Server must be EventSourcingDB'):
                await read_all_events(server)

            await read_all_events(server)

            assert server.probe_count == 2
            assert [request.path for request in server.requests] == ['/api/v2/data/read-events']

    @staticmethod
    @pytest.mark.asyncio
    async def test_fails_if_the_ping_stalls_and_asks_again_next_time() -> None:
        stalled = False

        async def answer_probe(request: web.Request) -> web.StreamResponse:
            nonlocal stalled
            if not stalled:
                stalled = True
                await asyncio.Event().wait()
            return await answer_probe_with_v2_api(request)

        async with v2_stream_server(answer_probe=answer_probe, stall_timeout=0.5) as server:
            with pytest.raises(ConnectionStalledError):
                async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                    await read_all_events(server)

            await read_all_events(server)

            assert server.probe_count == 2

    @staticmethod
    @pytest.mark.asyncio
    async def test_fails_if_the_server_is_unreachable_and_asks_again_once_it_is() -> None:
        port = get_random_available_port()

        async def write_stream(response: web.StreamResponse) -> None:
            await response.write(b'{"type":"end","data":{}}\n')

        async with Client(f'http://127.0.0.1:{port}', 'secret') as client:
            with pytest.raises(aiohttp.ClientConnectorError):
                async for _ in client.read_events('/', ReadEventsOptions(recursive=True)):
                    pass

            async with StreamServer(write_stream, api='v2', port=port) as reachable_server:
                async for _ in client.read_events('/', ReadEventsOptions(recursive=True)):
                    pass

                assert reachable_server.probe_count == 1
                assert [request.path for request in reachable_server.requests] == [
                    '/api/v2/data/read-events'
                ]

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ('answer_probe', 'expected_path'),
        [
            pytest.param(answer_probe_with_v2_api, '/api/v2/data/read-events', id='v2'),
            pytest.param(answer_probe_without_v2_api, '/api/v1/read-events', id='v1'),
        ],
    )
    async def test_shares_one_ping_between_concurrent_first_requests(
        answer_probe, expected_path: str
    ) -> None:
        probe_arrived = asyncio.Event()
        release_probe = asyncio.Event()

        async def answer_probe_once_released(request: web.Request) -> web.StreamResponse:
            probe_arrived.set()
            await release_probe.wait()
            return await answer_probe(request)

        async with v2_stream_server(answer_probe=answer_probe_once_released) as server:
            requests = [asyncio.create_task(read_all_events(server)) for _ in range(5)]

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await probe_arrived.wait()
                release_probe.set()
                await asyncio.gather(*requests, return_exceptions=True)

            assert server.probe_count == 1
            assert [request.path for request in server.requests] == [expected_path] * 5

    @staticmethod
    @pytest.mark.asyncio
    async def test_fails_concurrent_first_requests_with_the_error_of_their_shared_ping() -> None:
        probe_arrived = asyncio.Event()
        release_probe = asyncio.Event()
        failed = False

        async def answer_probe(request: web.Request) -> web.StreamResponse:
            nonlocal failed
            if failed:
                return await answer_probe_with_v2_api(request)

            failed = True
            probe_arrived.set()
            await release_probe.wait()
            return web.Response(status=500, text='internal server error', headers=SERVER_HEADER)

        async with v2_stream_server(answer_probe=answer_probe) as server:
            requests = [asyncio.create_task(read_all_events(server)) for _ in range(3)]

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await probe_arrived.wait()
                release_probe.set()
                results = await asyncio.gather(*requests, return_exceptions=True)

            assert [type(result) for result in results] == [DbApiError] * 3
            assert server.probe_count == 1
            assert server.requests == []

            await read_all_events(server)

            assert server.probe_count == 2

    @staticmethod
    @pytest.mark.asyncio
    async def test_keeps_the_ping_going_for_the_others_if_the_request_that_started_it_is_cancelled() -> None:
        probe_arrived = asyncio.Event()
        release_probe = asyncio.Event()

        async def answer_probe(request: web.Request) -> web.StreamResponse:
            probe_arrived.set()
            await release_probe.wait()
            return await answer_probe_with_v2_api(request)

        async with v2_stream_server(answer_probe=answer_probe) as server:
            first_request = asyncio.create_task(read_all_events(server))
            second_request = asyncio.create_task(read_all_events(server))

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await probe_arrived.wait()
                first_request.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first_request

                release_probe.set()
                await second_request

            assert server.probe_count == 1
            assert [request.path for request in server.requests] == ['/api/v2/data/read-events']

    @staticmethod
    @pytest.mark.asyncio
    async def test_logs_nothing_if_the_ping_fails_after_the_request_that_started_it_is_cancelled(
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        probe_arrived = asyncio.Event()
        release_probe = asyncio.Event()
        failed = False

        async def answer_probe(request: web.Request) -> web.StreamResponse:
            nonlocal failed
            if failed:
                return await answer_probe_with_v2_api(request)

            failed = True
            probe_arrived.set()
            await release_probe.wait()
            return web.Response(status=500, text='internal server error', headers=SERVER_HEADER)

        async with v2_stream_server(answer_probe=answer_probe) as server:
            first_request = asyncio.create_task(read_all_events(server))

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await probe_arrived.wait()
                first_request.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first_request

                # A request that comes while the ping runs shares it, and gets
                # its error once the ping is done.
                second_request = asyncio.create_task(read_all_events(server))
                release_probe.set()
                with pytest.raises(DbApiError):
                    await second_request

                await read_all_events(server)

            assert server.probe_count == 2

        assert [record for record in caplog.records if record.levelno >= logging.ERROR] == []


class TestApiDetectionAfterARollback:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('request_', REQUESTS_EXCEPT_PING_AND_WRITES)
    @pytest.mark.parametrize('status', [404, 405])
    @pytest.mark.parametrize(('headers', 'expected_error'), ANSWERED_BY)
    async def test_fails_once_with_the_404_or_405_of_the_v2_api_and_asks_again_on_the_next_request(
        request_: Request, status: int, headers: Mapping[str, str], expected_error: type[Exception]
    ) -> None:
        rollback = Rollback(status, headers)
        async with rollback.create_server() as server:
            client = server.get_client()
            await read_events(client)
            rollback.is_rolled_back = True

            with pytest.raises(CustomError) as error:
                await request_(client)

            assert type(error.value) is expected_error
            assert server.probe_count == 1
            assert apis_of(server) == ['v2', 'v2']

            await read_events(client)

            assert server.probe_count == 2
            assert apis_of(server) == ['v2', 'v2', 'v1']

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('request_', WRITES)
    @pytest.mark.parametrize('status', [404, 405])
    @pytest.mark.parametrize(('headers', 'expected_cause'), ANSWERED_BY)
    async def test_reports_an_unknown_outcome_for_a_write_and_asks_again_on_the_next_request(
        request_: Request, status: int, headers: Mapping[str, str], expected_cause: type[Exception]
    ) -> None:
        rollback = Rollback(status, headers)
        async with rollback.create_server() as server:
            client = server.get_client()
            await read_events(client)
            rollback.is_rolled_back = True

            with pytest.raises(OutcomeUnknownError) as error:
                await request_(client)

            assert type(error.value) is OutcomeUnknownError
            assert type(error.value.cause) is expected_cause
            assert server.probe_count == 1
            assert apis_of(server) == ['v2', 'v2']

            await read_events(client)

            assert server.probe_count == 2
            assert apis_of(server) == ['v2', 'v2', 'v1']

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('request_', REQUESTS_EXCEPT_PING)
    async def test_keeps_the_api_after_an_error_item_of_the_v2_api_which_comes_with_status_200(
        request_: Request,
    ) -> None:
        async def answer_with_error_item(_: web.Request) -> web.StreamResponse:
            return web.Response(text=EVENT_TYPE_UNKNOWN_ITEM, headers=SERVER_HEADER)

        rollback = Rollback()
        async with rollback.create_server() as server:
            client = server.get_client()
            await read_events(client)

            rollback.answer = answer_with_error_item
            with pytest.raises(DbApiError) as error:
                await request_(client)

            assert (error.value.status, error.value.code) == (200, ErrorCode.EVENT_TYPE_UNKNOWN)

            rollback.answer = answer_read_events
            await read_events(client)

            assert server.probe_count == 1

            # The same client forgets the API once the server is rolled back.
            rollback.is_rolled_back = True
            with pytest.raises(DbApiError):
                await read_events(client)
            await read_events(client)

            assert server.probe_count == 2
            assert apis_of(server) == ['v2', 'v2', 'v2', 'v2', 'v1']

    @staticmethod
    @pytest.mark.asyncio
    async def test_keeps_the_api_after_a_404_of_the_v1_api_which_it_uses_once_the_server_is_rolled_back() -> None:
        async def answer_event_type_unknown(_: web.Request) -> web.StreamResponse:
            return web.Response(status=404, text='event type not found', headers=SERVER_HEADER)

        rollback = Rollback()
        async with rollback.create_server() as server:
            client = server.get_client()
            await read_events(client)
            rollback.is_rolled_back = True
            with pytest.raises(DbApiError):
                await read_events(client)
            await read_events(client)

            # Through the v1 API, 404 is an error such as an unknown event type.
            rollback.answer = answer_event_type_unknown
            with pytest.raises(DbApiError) as error:
                await read_event_type(client)

            assert (error.value.status, error.value.code) == (404, ErrorCode.EVENT_TYPE_UNKNOWN)

            rollback.answer = answer_read_events
            await read_events(client)

            assert server.probe_count == 2
            assert apis_of(server) == ['v2', 'v2', 'v1', 'v1', 'v1']

    @staticmethod
    @pytest.mark.asyncio
    async def test_shares_the_ping_that_asks_again_and_keeps_its_answer_if_earlier_requests_fail_meanwhile() -> None:
        # Once the server is rolled back, the first ping waits until the test
        # releases it, and every later one is answered at once, so that a ping
        # too many shows in the number of pings.
        held_requests = HeldRequests()
        is_probe_held = False
        probe_arrived = asyncio.Event()
        release_probe = asyncio.Event()

        async def answer_probe(request: web.Request) -> web.StreamResponse:
            nonlocal is_probe_held
            if not held_requests.is_holding:
                return await answer_probe_with_v2_api(request)

            if not is_probe_held:
                is_probe_held = True
                probe_arrived.set()
                await release_probe.wait()
            return answer_without_v2_api()

        async with StreamServer(
            None, answer_probe=answer_probe, answer=held_requests.answer
        ) as server:
            client = server.get_client()
            await read_events(client)
            held_requests.is_holding = True

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                fails_first, release_first = await held_requests.send(client)
                fails_while_asking, release_while_asking = await held_requests.send(client)
                fails_after_asking, release_after_asking = await held_requests.send(client)

                release_first.set_result(None)
                with pytest.raises(DbApiError):
                    await fails_first

                waits_from_before = asyncio.create_task(read_events(client))
                await probe_arrived.wait()

                release_while_asking.set_result(None)
                with pytest.raises(DbApiError):
                    await fails_while_asking

                # Lets the request get as far as waiting for the ping.
                waits_from_after = asyncio.create_task(read_events(client))
                await asyncio.sleep(0)

                release_probe.set()
                await asyncio.gather(waits_from_before, waits_from_after)

                release_after_asking.set_result(None)
                with pytest.raises(DbApiError):
                    await fails_after_asking

                await read_events(client)

            assert server.probe_count == 2
            assert apis_of(server) == ['v2', 'v2', 'v2', 'v2', 'v1', 'v1', 'v1']

    @staticmethod
    @pytest.mark.asyncio
    async def test_keeps_the_v2_api_that_a_newer_ping_found_if_an_earlier_request_fails_after_it() -> None:
        # As if the server answered paths of the v2 API with 404 only for a
        # moment, such as while it is deployed anew.
        held_requests = HeldRequests()

        async with StreamServer(None, api='v2', answer=held_requests.answer) as server:
            client = server.get_client()
            await read_events(client)
            held_requests.is_holding = True

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                fails_first, release_first = await held_requests.send(client)
                fails_later, release_later = await held_requests.send(client)
                held_requests.is_holding = False

                release_first.set_result(None)
                with pytest.raises(DbApiError):
                    await fails_first

                await read_events(client)

                release_later.set_result(None)
                with pytest.raises(DbApiError):
                    await fails_later

                await read_events(client)

            assert server.probe_count == 2
            assert apis_of(server) == ['v2', 'v2', 'v2', 'v2', 'v2']


class TestApiDetectionForARecursivePrecondition:
    # Only the v2 API checks a recursive precondition, and a server that did
    # not offer it may offer it by now, for example after an upgrade.
    RECURSIVE = IsSubjectPristine('/books', PreconditionOptions(recursive=True))

    @staticmethod
    @pytest.mark.asyncio
    async def test_asks_again_and_writes_through_the_v2_api_once_the_server_offers_it() -> None:
        async with StreamServer(
            None,
            answer_probe=answer_probes_in_turn(
                answer_probe_without_v2_api, answer_probe_with_v2_api
            ),
            answer=answer_writes_and_read_events,
        ) as server:
            client = server.get_client()
            await read_events(client)

            await write_events_with(client, TestApiDetectionForARecursivePrecondition.RECURSIVE)

            assert server.probe_count == 2
            assert [(request.method, request.path) for request in server.requests] == [
                ('POST', '/api/v1/read-events'),
                ('POST', '/api/v2/data/write-events'),
            ]
            assert json.loads(server.requests[-1].body)['preconditions'] == [
                {
                    'type': 'isSubjectPristine',
                    'payload': {'subject': '/books', 'options': {'recursive': True}},
                }
            ]

            await read_events(client)

            assert server.probe_count == 2
            assert apis_of(server) == ['v1', 'v2', 'v2']

    @staticmethod
    @pytest.mark.asyncio
    async def test_asks_again_and_refuses_the_write_if_the_server_still_lacks_the_v2_api() -> None:
        async with StreamServer(None, answer=answer_writes_and_read_events) as server:
            client = server.get_client()
            await read_events(client)

            with pytest.raises(IncompatibleServerError):
                await write_events_with(client, TestApiDetectionForARecursivePrecondition.RECURSIVE)

            assert server.probe_count == 2
            assert apis_of(server) == ['v1']

            await read_events(client)

            assert server.probe_count == 2
            assert apis_of(server) == ['v1', 'v1']

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'precondition',
        [
            pytest.param(IsSubjectPristine('/books'), id='without options'),
            pytest.param(
                IsSubjectPristine('/books', PreconditionOptions(recursive=False)),
                id='not recursive',
            ),
        ],
    )
    async def test_keeps_the_answer_for_a_write_without_a_recursive_precondition(
        precondition: Precondition,
    ) -> None:
        async with StreamServer(
            None,
            answer_probe=answer_probes_in_turn(
                answer_probe_without_v2_api, answer_probe_with_v2_api
            ),
            answer=answer_writes_and_read_events,
        ) as server:
            client = server.get_client()
            await read_events(client)

            await write_events_with(client, precondition)

            assert server.probe_count == 1
            assert apis_of(server) == ['v1', 'v1']

    @staticmethod
    @pytest.mark.asyncio
    async def test_lets_every_other_request_use_the_answer_while_it_asks_again() -> None:
        probe_arrived = asyncio.Event()
        release_probe = asyncio.Event()

        async def answer_probe_once_released(request: web.Request) -> web.StreamResponse:
            probe_arrived.set()
            await release_probe.wait()
            return await answer_probe_with_v2_api(request)

        async with StreamServer(
            None,
            answer_probe=answer_probes_in_turn(
                answer_probe_without_v2_api, answer_probe_once_released
            ),
            answer=answer_writes_and_read_events,
        ) as server:
            client = server.get_client()
            await read_events(client)

            write = asyncio.create_task(
                write_events_with(client, TestApiDetectionForARecursivePrecondition.RECURSIVE)
            )
            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await probe_arrived.wait()

            read = asyncio.create_task(read_events(client))
            done, _ = await asyncio.wait({read}, timeout=GUARD_TIMEOUT_SECONDS)
            did_read_while_asking = read in done

            release_probe.set()
            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await asyncio.gather(read, write)

            assert did_read_while_asking, 'The read waited for the ping that asks again.'
            assert server.probe_count == 2
            assert apis_of(server) == ['v1', 'v1', 'v2']

    @staticmethod
    @pytest.mark.asyncio
    async def test_keeps_the_answer_if_asking_again_fails() -> None:
        async with StreamServer(
            None,
            answer_probe=answer_probes_in_turn(
                answer_probe_without_v2_api,
                answer_probe_with_status(500, 'internal server error'),
                answer_probe_without_v2_api,
            ),
            answer=answer_writes_and_read_events,
        ) as server:
            client = server.get_client()
            await read_events(client)

            with pytest.raises(DbApiError) as error:
                await write_events_with(client, TestApiDetectionForARecursivePrecondition.RECURSIVE)

            assert error.value.status == 500
            assert server.probe_count == 2
            assert apis_of(server) == ['v1']

            await read_events(client)

            assert server.probe_count == 2
            assert apis_of(server) == ['v1', 'v1']

    @staticmethod
    @pytest.mark.asyncio
    async def test_shares_the_ping_that_asks_again_between_concurrent_writes() -> None:
        probe_arrived = asyncio.Event()
        release_probe = asyncio.Event()

        async def answer_probe_once_released(request: web.Request) -> web.StreamResponse:
            probe_arrived.set()
            await release_probe.wait()
            return await answer_probe_with_v2_api(request)

        async with StreamServer(
            None,
            answer_probe=answer_probes_in_turn(
                answer_probe_without_v2_api, answer_probe_once_released
            ),
            answer=answer_writes_and_read_events,
        ) as server:
            client = server.get_client()
            await read_events(client)

            writes = [
                asyncio.create_task(
                    write_events_with(client, TestApiDetectionForARecursivePrecondition.RECURSIVE)
                )
                for _ in range(3)
            ]

            async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                await probe_arrived.wait()
                release_probe.set()
                await asyncio.gather(*writes)

            assert server.probe_count == 2
            assert [request.path for request in server.requests] == [
                '/api/v1/read-events',
                *['/api/v2/data/write-events'] * 3,
            ]


class TestApiDetectionAgainstEventSourcingDB:
    @staticmethod
    @pytest.mark.asyncio
    async def test_speaks_the_api_that_the_server_offers(database: Database) -> None:
        # Whether the server offers the v2 API is found out without the client
        # SDK, rather than from the tag of the image, since every version from
        # 1.3 on offers it, and still offers the v1 API as well.
        expected_api_version = 'v2' if await database.offers_v2_api() else 'v1'
        client = database.get_client()

        async for _ in client.read_event_types():
            pass

        assert await client._get_api_version() == expected_api_version
