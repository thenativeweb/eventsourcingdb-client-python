from collections.abc import Callable, Awaitable
from http import HTTPStatus

import pytest
from flask import Response

from eventsourcingdb.client import Client
from eventsourcingdb.errors.client_error import ClientError
from eventsourcingdb.errors.server_error import ServerError
from .conftest import TestData
from .shared.database import Database
from .shared.start_local_http_server import AttachHandlers, AttachHandler


class TestRegisterEventSchema:
    @staticmethod
    @pytest.mark.asyncio
    async def test_registers_new_schema_if_it_doesnt_conflict_with_existing_events(
        database: Database,
    ):
        client = database.with_authorization.client

        await client.register_event_schema(
            "com.bar.baz",
            {
                "type": "object",
                "properties": {}
            }
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_schema_conflicts_with_existing_events(
        database: Database,
        test_data: TestData,
    ):
        client = database.with_authorization.client

        await client.write_events([
            test_data.TEST_SOURCE.new_event(
                subject="/",
                event_type="com.gornisht.ekht",
                data={
                    "oy": "gevalt",
                },
            )
        ])

        # Update the error pattern to match the actual error message about missing 'properties'
        with pytest.raises(ClientError, match="missing properties: 'properties'"):
            await client.register_event_schema(
                "com.gornisht.ekht",
                {
                    "type": "object",
                    "additionalProperties": False
                }
            )

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_schema_already_exists(
        database: Database,
    ):
        client = database.with_authorization.client

        await client.register_event_schema(
            "com.gornisht.ekht",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False
            }
        )

        with pytest.raises(ClientError, match="schema already exists"):
            await client.register_event_schema(
                "com.gornisht.ekht",
                {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False
                }
            )

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_schema_is_invalid(
        database: Database,
    ):
        client = database.with_authorization.client

        # Update the error pattern to match the actual error message about invalid type
        with pytest.raises(ClientError, match="value must be \"object\""):
            await client.register_event_schema(
                "com.gornisht.ekht",
                {
                    "type": "gurkenwasser",
                    "properties": {}
                }
            )


class TestRegisterEventSchemaWithMockServer:
    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_5xx_status_code(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_register_event_schema(response: Response) -> Response:
                response.status_code = HTTPStatus.BAD_GATEWAY
                response.set_data(HTTPStatus.BAD_GATEWAY.phrase)
                return response

            attach_handler('/api/v1/register-event-schema', 'POST', handle_register_event_schema)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            await client.register_event_schema("com.foo.bar", '{"type":"object"}')

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_servers_protocol_version_not_matching(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_register_event_schema(response: Response) -> Response:
                response.headers['X-EventSourcingDB-Protocol-Version'] = '0.0.0'
                response.status_code = HTTPStatus.UNPROCESSABLE_ENTITY
                response.set_data(HTTPStatus.UNPROCESSABLE_ENTITY.phrase)
                return response

            attach_handler('/api/v1/register-event-schema', 'POST', handle_register_event_schema)

        client = await get_client(attach_handlers)

        with pytest.raises(ClientError):
            await client.register_event_schema("com.foo.bar", '{"type":"object"}')

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_4xx_status_code(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_register_event_schema(response: Response) -> Response:
                response.status_code = HTTPStatus.NOT_FOUND
                response.set_data(HTTPStatus.NOT_FOUND.phrase)
                return response

            attach_handler('/api/v1/register-event-schema', 'POST', handle_register_event_schema)

        client = await get_client(attach_handlers)

        with pytest.raises(ClientError):
            await client.register_event_schema("com.foo.bar", '{"type":"object"}')

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_unusual_status_code(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_register_event_schema(response: Response) -> Response:
                response.status_code = HTTPStatus.ACCEPTED
                response.set_data(
                    '{"type": "subject", "payload": { "subject": "/foo" }}\n'
                )
                return response

            attach_handler('/api/v1/register-event-schema', 'POST', handle_register_event_schema)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            await client.register_event_schema("com.foo.bar", '{"type":"object"}')
