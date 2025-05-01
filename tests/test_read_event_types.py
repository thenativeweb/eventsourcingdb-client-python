from collections.abc import Callable, Awaitable
from http import HTTPStatus

import pytest
from flask import Response

from eventsourcingdb.client import Client
from eventsourcingdb.errors.client_error import ClientError
from eventsourcingdb.errors.server_error import ServerError
from eventsourcingdb.event.event_candidate import EventCandidate
from eventsourcingdb.handlers.read_event_types.event_type import EventType
from .conftest import TestData
from .shared.database import Database
from .shared.start_local_http_server import AttachHandlers, AttachHandler


class TestReadEventTypes:
    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_all_types_of_existing_events_and_registered_schemas(
        database: Database,
        test_data: TestData,
    ):
        client = database.get_client("with_authorization")

        await client.write_events([
            EventCandidate(
                source=test_data.TEST_SOURCE_STRING,
                subject="/account",
                type="com.foo.bar",
                data={},
            ),
            EventCandidate(
                source=test_data.TEST_SOURCE_STRING,
                subject="/account/user",
                type="com.bar.baz",
                data={},
            ),
            EventCandidate(
                source=test_data.TEST_SOURCE_STRING,
                subject="/account/user",
                type="com.baz.leml",
                data={},
            ),
            EventCandidate(
                source=test_data.TEST_SOURCE_STRING,
                subject="/",
                type="com.quux.knax",
                data={},
            ),
        ])

        await client.register_event_schema(
            "org.ban.ban",
            {"type": "object", "properties": {}}
        )
        await client.register_event_schema(
            "org.bing.chilling",
            {"type": "object", "properties": {}}
        )

        actual_event_types: set[EventType] = set()
        async for event_type in client.read_event_types():
            actual_event_types.add(event_type)

        expected_event_types = {
            EventType(
                event_type="com.foo.bar",
                is_phantom=False,
                schema=None,
            ),
            EventType(
                event_type="com.bar.baz",
                is_phantom=False,
                schema=None,
            ),
            EventType(
                event_type="com.baz.leml",
                is_phantom=False,
                schema=None,
            ),
            EventType(
                event_type="com.quux.knax",
                is_phantom=False,
                schema=None,
            ),
            EventType(
                event_type="org.ban.ban",
                is_phantom=True,
                schema={"type": "object", "properties": {}},  # Updated expected schema
            ),
            EventType(
                event_type="org.bing.chilling",
                is_phantom=True,
                schema={"type": "object", "properties": {}},  # Updated expected schema
            ),
        }

        assert actual_event_types == expected_event_types


class TestReadEvenTypesWithMockServer:
    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_5xx_status_code(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_event_types(response: Response) -> Response:
                response.status_code = HTTPStatus.BAD_GATEWAY
                response.set_data(HTTPStatus.BAD_GATEWAY.phrase)
                return response

            attach_handler('/api/v1/read-event-types', 'POST', handle_read_event_types)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.read_event_types():
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_servers_protocol_version_not_matching(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_event_types(response: Response) -> Response:
                response.headers['X-EventSourcingDB-Protocol-Version'] = '0.0.0'
                response.status_code = HTTPStatus.UNPROCESSABLE_ENTITY
                response.set_data(HTTPStatus.UNPROCESSABLE_ENTITY.phrase)
                return response

            attach_handler('/api/v1/read-event-types', 'POST', handle_read_event_types)

        client = await get_client(attach_handlers)

        with pytest.raises(ClientError):
            async for _ in client.read_event_types():
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_4xx_status_code(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_event_types(response: Response) -> Response:
                response.status_code = HTTPStatus.NOT_FOUND
                response.set_data(HTTPStatus.NOT_FOUND.phrase)
                return response

            attach_handler('/api/v1/read-event-types', 'POST', handle_read_event_types)

        client = await get_client(attach_handlers)

        with pytest.raises(ClientError):
            async for _ in client.read_event_types():
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_unusual_status_code(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_event_types(response: Response) -> Response:
                response.status_code = HTTPStatus.ACCEPTED
                response.set_data(
                    '{"type": "subject", "payload": { "subject": "/foo" }}\n'
                )
                return response

            attach_handler('/api/v1/read-event-types', 'POST', handle_read_event_types)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.read_event_types():
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_item_that_cannot_be_unmarshalled(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_event_types(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('cannot be parsed')
                return response

            attach_handler('/api/v1/read-event-types', 'POST', handle_read_event_types)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.read_event_types():
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_unsupported_item(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_event_types(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data(
                    '{ "type": "clown", "payload": { "task": "emotional support" }')
                return response

            attach_handler('/api/v1/read-event-types', 'POST', handle_read_event_types)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.read_event_types():
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_an_error_item(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_event_types(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data(
                    '{ "type": "error", "payload": { "error": "some error happened" }')
                return response

            attach_handler('/api/v1/read-event-types', 'POST', handle_read_event_types)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.read_event_types():
                pass
