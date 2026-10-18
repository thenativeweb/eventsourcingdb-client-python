import asyncio
import logging

import aiohttp
import pytest
from aiohttp import web

from eventsourcingdb import (
    Client,
    ConnectionStalledError,
    DbApiError,
    ReadEventsOptions,
    ReadSubjectsOptions,
    ServerError,
)

from .shared.database import Database
from .shared.stream_server import (
    SERVER_HEADER,
    StreamServer,
    answer_probe_with_v2_api,
    answer_probe_without_v2_api,
)
from .shared.util.get_random_available_port import get_random_available_port

GUARD_TIMEOUT_SECONDS = 5


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
    async def test_speaks_the_v1_api_if_a_proxy_that_only_forwards_it_answers_the_ping(
        status: int,
    ) -> None:
        async def answer_probe_as_proxy(_: web.Request) -> web.StreamResponse:
            return web.Response(status=status, text='not found', headers={'Server': 'nginx'})

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
