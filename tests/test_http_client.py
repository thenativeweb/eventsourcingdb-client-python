from http import HTTPStatus
from collections.abc import Awaitable, Callable

import pytest

from eventsourcingdb.errors.client_error import ClientError
from eventsourcingdb.errors.server_error import ServerError
from eventsourcingdb.http_client.http_client import HttpClient
from .shared.start_local_http_server import \
    AttachHandler, \
    Response, \
    AttachHandlers


class TestHttpClient:
    @staticmethod
    @pytest.mark.asyncio
    async def test_gets_correct_response_for_get_request(
        get_http_client: Callable[[AttachHandlers], Awaitable[HttpClient]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_root(res: Response) -> Response:
                res.status_code = HTTPStatus.OK
                res.set_data(HTTPStatus.OK.phrase)
                return res

            attach_handler('/', 'GET', handle_root)

        http_client = await get_http_client(attach_handlers)

        with await http_client.get('/') as response:
            body_bytes = await response.body.read()
            body_text = body_bytes.decode('utf-8')
            assert body_text == HTTPStatus.OK.phrase

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_server_error_for_get_request_with_5xx_response(
        get_http_client: Callable[[AttachHandlers], Awaitable[HttpClient]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_root(res: Response) -> Response:
                res.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
                return res

            attach_handler('/', 'GET', handle_root)

        http_client = await get_http_client(attach_handlers)

        with pytest.raises(ServerError):
            with await http_client.get('/'):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_client_error_for_get_request_with_4xx_response(
        get_http_client: Callable[[AttachHandlers], Awaitable[HttpClient]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_root(res: Response) -> Response:
                res.status_code = HTTPStatus.BAD_REQUEST
                return res

            attach_handler('/', 'GET', handle_root)

        http_client = await get_http_client(attach_handlers)

        with pytest.raises(ClientError):
            with await http_client.get('/'):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_gets_correct_response_for_post_request(
        get_http_client: Callable[[AttachHandlers], Awaitable[HttpClient]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_root(res: Response) -> Response:
                res.status_code = HTTPStatus.OK
                res.set_data(HTTPStatus.OK.phrase)
                return res

            attach_handler('/', 'POST', handle_root)

        http_client = await get_http_client(attach_handlers)

        with await http_client.post('/', '') as response:
            body_bytes = await response.body.read()
            body_text = body_bytes.decode('utf-8')
            assert body_text == HTTPStatus.OK.phrase
