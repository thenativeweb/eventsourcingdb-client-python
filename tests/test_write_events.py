from collections.abc import Callable, Awaitable
from http import HTTPStatus

import pytest

from eventsourcingdb_client_python.client import Client
from eventsourcingdb_client_python.errors.client_error import ClientError
from eventsourcingdb_client_python.errors.invalid_parameter_error import InvalidParameterError
from eventsourcingdb_client_python.errors.server_error import ServerError
from eventsourcingdb_client_python.event.source import Source
from eventsourcingdb_client_python.handlers.write_events import \
    IsSubjectPristinePrecondition, \
    IsSubjectOnEventIdPrecondition

from .shared.build_database import build_database
from .shared.database import Database
from .shared.event.test_source import TEST_SOURCE
from .shared.start_local_http_server import \
    AttachHandler, \
    Response, \
    AttachHandlers


class TestWriteSubjects:
    test_source = Source(TEST_SOURCE)

    @classmethod
    def setup_class(cls):
        build_database('tests/shared/docker/eventsourcingdb')

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_an_error_if_server_is_not_reachable(
        database: Database
    ):
        client = database.with_invalid_url.client

        with pytest.raises(ServerError):
            await client.write_events([
                TestWriteSubjects.test_source.new_event(
                    subject='/',
                    event_type='com.foo.bar',
                    data={}
                )
            ])

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_an_error_for_empty_event_candidates(
        database: Database
    ):
        client = database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            await client.write_events([])

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_an_error_for_malformed_subject(
        database: Database
    ):
        client = database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            await client.write_events([
                TestWriteSubjects.test_source.new_event(
                    subject='',
                    event_type='com.foo.bar',
                    data={}
                )
            ])

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_an_error_for_malformed_type(
        database: Database
    ):
        client = database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            await client.write_events([
                TestWriteSubjects.test_source.new_event(
                    subject='/',
                    event_type='',
                    data={}
                )
            ])

    @staticmethod
    @pytest.mark.asyncio
    async def test_supports_authorization(
        database: Database
    ):
        client = database.with_authorization.client

        await client.write_events([
            TestWriteSubjects.test_source.new_event(
                subject='/',
                event_type='com.foo.bar',
                data={}
            )
        ])

    @staticmethod
    @pytest.mark.asyncio
    async def test_is_pristine_precondition_works_for_new_subject(
        database: Database
    ):
        client = database.with_authorization.client

        await client.write_events([
            TestWriteSubjects.test_source.new_event(
                subject='/',
                event_type='com.foo.bar',
                data={}
            )],
            [IsSubjectPristinePrecondition('/')]
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_is_pristine_precondition_fails_for_existing_subject(
        database: Database
    ):
        client = database.with_authorization.client

        await client.write_events([
            TestWriteSubjects.test_source.new_event(
                subject='/',
                event_type='com.foo.bar',
                data={}
            )]
        )

        with pytest.raises(ClientError):
            await client.write_events([
                TestWriteSubjects.test_source.new_event(
                    subject='/',
                    event_type='com.foo.bar',
                    data={}
                )],
                [IsSubjectPristinePrecondition('/')]
            )

    @staticmethod
    @pytest.mark.asyncio
    async def test_is_on_event_id_precondition_works_for_correct_id(
        database: Database
    ):
        client = database.with_authorization.client

        await client.write_events([
            TestWriteSubjects.test_source.new_event(
                subject='/',
                event_type='com.foo.bar',
                data={}
            )]
        )

        await client.write_events([
            TestWriteSubjects.test_source.new_event(
                subject='/',
                event_type='com.foo.bar',
                data={}
            )],
            [IsSubjectOnEventIdPrecondition('/', '0')]
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_is_subject_on_event_id_fails_for_wrong_id(
        database: Database
    ):
        client = database.with_authorization.client

        await client.write_events([
            TestWriteSubjects.test_source.new_event(
                subject='/',
                event_type='com.foo.bar',
                data={}
            )]
        )

        with pytest.raises(ClientError):
            await client.write_events([
                TestWriteSubjects.test_source.new_event(
                    subject='/',
                    event_type='com.foo.bar',
                    data={}
                )],
                [IsSubjectOnEventIdPrecondition('/', '2')]
            )


class TestWriteEventsWithMockServer:
    test_source = Source(TEST_SOURCE)
    events = [test_source.new_event('/', 'com.foo.bar', {})]

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_5xx_status_code(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_write_events(response: Response) -> Response:
                response.status_code = HTTPStatus.BAD_GATEWAY
                response.set_data(HTTPStatus.BAD_GATEWAY.phrase)
                return response

            attach_handler('/api/write-events', 'POST', handle_write_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            await client.write_events(TestWriteEventsWithMockServer.events)

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_protocol_version_does_not_match(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_write_events(response: Response) -> Response:
                response.headers['X-EventSourcingDB-Protocol-Version'] = '0.0.0'
                response.status_code = HTTPStatus.UNPROCESSABLE_ENTITY
                response.set_data(HTTPStatus.UNPROCESSABLE_ENTITY.phrase)
                return response

            attach_handler('/api/write-events', 'POST', handle_write_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ClientError):
            await client.write_events(TestWriteEventsWithMockServer.events)

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_4xx_status_code(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_write_events(response: Response) -> Response:
                response.status_code = HTTPStatus.NOT_FOUND
                response.set_data(HTTPStatus.NOT_FOUND.phrase)
                return response

            attach_handler('/api/write-events', 'POST', handle_write_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ClientError):
            await client.write_events(TestWriteEventsWithMockServer.events)

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_unexpected_status_code(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_write_events(response: Response) -> Response:
                response.status_code = HTTPStatus.ACCEPTED
                response.set_data(HTTPStatus.ACCEPTED.phrase)
                return response

            attach_handler('/api/write-events', 'POST', handle_write_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            await client.write_events(TestWriteEventsWithMockServer.events)

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_response_cannot_be_parsed(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_write_events(response: Response) -> Response:
                response.set_data('this is not data')
                return response

            attach_handler('/api/write-events', 'POST', handle_write_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            await client.write_events(TestWriteEventsWithMockServer.events)
