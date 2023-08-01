from collections.abc import Callable, Awaitable
from http import HTTPStatus

import pytest

from eventsourcingdb_client_python.client import Client
from eventsourcingdb_client_python.errors.client_error import ClientError
from eventsourcingdb_client_python.errors.invalid_parameter_error import InvalidParameterError
from eventsourcingdb_client_python.errors.server_error import ServerError
from eventsourcingdb_client_python.event.event_candidate import EventCandidate

from .shared.build_database import build_database
from .shared.database import Database
from .shared.event.test_source import TEST_SOURCE
from .shared.start_local_http_server import \
    AttachHandler, \
    Response, \
    AttachHandlers


class TestReadSubjects:
    @classmethod
    def setup_class(cls):
        build_database('tests/shared/docker/eventsourcingdb')

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_is_not_reachable(
        database: Database
    ):
        client = database.with_invalid_url.client

        with pytest.raises(ServerError):
            async for _ in client.read_subjects('/'):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_supports_authorization(
        database: Database
    ):
        client = database.with_authorization.client

        async for _ in client.read_subjects('/'):
            pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_all_subjects_starting_from_root(
        database: Database
    ):
        client = database.with_authorization.client

        await client.write_events([
            EventCandidate(
                TEST_SOURCE,
                '/foo',
                'io.thenativeweb.user.janeDoe.loggedIn',
                {}
            )
        ])

        actual_subjects = []
        async for subject in client.read_subjects('/'):
            actual_subjects.append(subject)

        assert actual_subjects == ['/', '/foo']

    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_all_subjects_starting_from_given_base_subject(
        database: Database
    ):
        client = database.with_authorization.client

        await client.write_events([
            EventCandidate(
                TEST_SOURCE,
                '/foo/bar',
                'io.thenativeweb.user.janeDoe.loggedIn',
                {}
            )
        ])

        actual_subjects = []
        async for subject in client.read_subjects('/foo'):
            actual_subjects.append(subject)

        assert actual_subjects == ['/foo', '/foo/bar']

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_an_error_if_base_subject_malformed(
        database: Database
    ):
        client = database.with_authorization.client

        await client.write_events([
            EventCandidate(
                TEST_SOURCE,
                '/foo/bar',
                'io.thenativeweb.user.janeDoe.loggedIn',
                {}
            )
        ])

        with pytest.raises(InvalidParameterError):
            async for _ in client.read_subjects(''):
                pass


class TestReadSubjectsWithMockServer:
    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_5xx_status_code(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_subjects(response: Response) -> Response:
                response.status_code = HTTPStatus.BAD_GATEWAY
                response.set_data(HTTPStatus.BAD_GATEWAY.phrase)
                return response

            attach_handler('/api/read-subjects', 'POST', handle_read_subjects)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.read_subjects('/'):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_servers_protocol_version_not_matching(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_subjects(response: Response) -> Response:
                response.headers['X-EventSourcingDB-Protocol-Version'] = '0.0.0'
                response.status_code = HTTPStatus.UNPROCESSABLE_ENTITY
                response.set_data(HTTPStatus.UNPROCESSABLE_ENTITY.phrase)
                return response

            attach_handler('/api/read-subjects', 'POST', handle_read_subjects)

        client = await get_client(attach_handlers)

        with pytest.raises(ClientError):
            async for _ in client.read_subjects('/'):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_4xx_status_code(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_subjects(response: Response) -> Response:
                response.status_code = HTTPStatus.NOT_FOUND
                response.set_data(HTTPStatus.NOT_FOUND.phrase)
                return response

            attach_handler('/api/read-subjects', 'POST', handle_read_subjects)

        client = await get_client(attach_handlers)

        with pytest.raises(ClientError):
            async for _ in client.read_subjects('/'):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_unusual_status_code(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_subjects(response: Response) -> Response:
                response.status_code = HTTPStatus.ACCEPTED
                response.set_data(
                    '{"type": "subject", "payload": { "subject": "/foo" }}\n'
                )
                return response

            attach_handler('/api/read-subjects', 'POST', handle_read_subjects)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.read_subjects('/'):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_item_that_cannot_be_unmarshalled(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_subjects(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('cannot be parsed')
                return response

            attach_handler('/api/read-subjects', 'POST', handle_read_subjects)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.read_subjects('/'):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_unsupported_item(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_subjects(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data(
                    '{ "type": "clown", "payload": { "task": "emotional support" }')
                return response

            attach_handler('/api/read-subjects', 'POST', handle_read_subjects)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.read_subjects('/'):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_an_error_item(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_subjects(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data(
                    '{ "type": "error", "payload": { "error": "some error happened" }')
                return response

            attach_handler('/api/read-subjects', 'POST', handle_read_subjects)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.read_subjects('/'):
                pass
