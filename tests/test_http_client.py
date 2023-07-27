from http import HTTPStatus

import pytest

from eventsourcingdb_client_python.errors.server_error import ServerError
from .shared.start_local_http_server import \
    AttachHandler, \
    Response, \
    start_local_http_server, \
    StopServer


class TestHttpClient:
    stop_server: StopServer = lambda: None

    @staticmethod
    def teardown_method():
        TestHttpClient.stop_server()

    @staticmethod
    @pytest.mark.asyncio
    async def test_gets_correct_response_for_get_request():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_root(res: Response) -> Response:
                res.status_code = HTTPStatus.OK
                res.set_data(HTTPStatus.OK.phrase)
                return res

            attach_handler('/', 'GET', handle_root)

        client, stop_server = await start_local_http_server(attach_handlers)
        http_client = client.http_client
        TestHttpClient.stop_server = stop_server

        async with await http_client.get('/') as response:
            body_bytes = await response.body.read()
            body_text = body_bytes.decode('utf-8')
            assert body_text == HTTPStatus.OK.phrase

    @staticmethod
    @pytest.mark.asyncio
    async def test_gets_correct_response_for_post_request():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_root(res: Response) -> Response:
                res.status_code = HTTPStatus.OK
                res.set_data(HTTPStatus.OK.phrase)
                return res

            attach_handler('/', 'POST', handle_root)

        client, stop_server = await start_local_http_server(attach_handlers)
        http_client = client.http_client
        TestHttpClient.stop_server = stop_server

        async with await http_client.post('/', '') as response:
            body_bytes = await response.body.read()
            body_text = body_bytes.decode('utf-8')
            assert body_text == HTTPStatus.OK.phrase
