from collections.abc import Callable, Awaitable
from http import HTTPStatus

import pytest

from eventsourcingdb_client_python.client import Client
from eventsourcingdb_client_python.errors.server_error import ServerError
from .shared.database import Database
from .shared.start_local_http_server import \
    AttachHandler, \
    Response, \
    AttachHandlers


class TestPing:
    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_no_error_if_server_is_reachable(database: Database):
        client = database.with_authorization.client

        await client.ping()

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_is_not_reachable(database: Database):
        client = database.with_invalid_url.client

        with pytest.raises(ServerError):
            await client.ping()

    @staticmethod
    @pytest.mark.asyncio
    async def test_supports_authorization(database: Database):
        client = database.with_authorization.client

        await client.ping()


class TestPingWithMockServer:

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_unexpected_status_code(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_ping(response: Response) -> Response:
                response.status_code = HTTPStatus.BAD_GATEWAY
                response.set_data('OK')
                return response

            attach_handler('/ping', 'GET', handle_ping)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            await client.ping()

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_respond_body_is_not_ok(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_ping(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('not OK')
                return response

            attach_handler('/ping', 'GET', handle_ping)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            await client.ping()
