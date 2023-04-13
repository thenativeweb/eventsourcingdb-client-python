from http import HTTPStatus

import pytest

from eventsourcingdb_client_python.errors.server_error import ServerError

from .shared.build_database import build_database
from .shared.database import Database
from .shared.start_local_http_server import \
    AttachHandler,\
    Response,\
    start_local_http_server,\
    StopServer


class TestPing:
    database: Database

    @classmethod
    def setup_class(cls):
        build_database('tests/shared/docker/eventsourcingdb')

    @staticmethod
    def setup_method():
        TestPing.database = Database()

    @staticmethod
    def teardown_method():
        TestPing.database.stop()

    @staticmethod
    def test_throws_no_error_if_server_is_reachable():
        client = TestPing.database.without_authorization.client

        client.ping()

    @staticmethod
    def test_throws_error_if_server_is_not_reachable():
        client = TestPing.database.with_invalid_url.client

        with pytest.raises(ServerError):
            client.ping()

    @staticmethod
    def test_supports_authorization():
        client = TestPing.database.with_authorization.client

        client.ping()


class TestPingWithMockServer:
    stop_server: StopServer = lambda: None

    @staticmethod
    def teardown_method():
        TestPingWithMockServer.stop_server()

    @staticmethod
    def test_throws_error_if_server_responds_with_unexpected_status_code():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_ping(response: Response) -> Response:
                response.status_code = HTTPStatus.BAD_GATEWAY
                response.set_data('OK')
                return response

            attach_handler('/ping', 'GET', handle_ping)

        client, stop_server = start_local_http_server(attach_handlers)
        TestPingWithMockServer.stop_server = stop_server

        with pytest.raises(ServerError):
            client.ping()

    @staticmethod
    def test_throws_error_if_server_respond_body_is_not_ok():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_ping(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('not OK')
                return response

            attach_handler('/ping', 'GET', handle_ping)

        client, stop_server = start_local_http_server(attach_handlers)
        TestPingWithMockServer.stop_server = stop_server

        with pytest.raises(ServerError):
            client.ping()
