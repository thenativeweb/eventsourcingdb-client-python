from http import HTTPStatus

import pytest

from eventsourcingdb_client_python.errors.client_error import ClientError
from eventsourcingdb_client_python.errors.invalid_parameter_error import InvalidParameterError
from eventsourcingdb_client_python.errors.server_error import ServerError
from eventsourcingdb_client_python.event.source import Source

from .shared.build_database import build_database
from .shared.database import Database
from .shared.event.test_source import TEST_SOURCE
from .shared.start_local_http_server import \
    StopServer,\
    AttachHandler,\
    Response,\
    start_local_http_server


class TestWriteSubjects:
    database: Database
    test_source = Source(TEST_SOURCE)

    @classmethod
    def setup_class(cls):
        build_database('tests/shared/docker/eventsourcingdb')

    @staticmethod
    def setup_method():
        TestWriteSubjects.database = Database()

    @staticmethod
    def teardown_method():
        TestWriteSubjects.database.stop()

    @staticmethod
    def test_throws_an_error_if_server_is_not_reachable():
        client = TestWriteSubjects.database.with_invalid_url.client

        with pytest.raises(ServerError):
            client.write_events([
                TestWriteSubjects.test_source.new_event(
                    subject='/',
                    event_type='com.foo.bar',
                    data={}
                )
            ])

    @staticmethod
    def test_throws_an_error_for_empty_event_candidates():
        client = TestWriteSubjects.database.without_authorization.client

        with pytest.raises(InvalidParameterError):
            client.write_events([])

    @staticmethod
    def test_throws_an_error_for_malformed_subject():
        client = TestWriteSubjects.database.without_authorization.client

        with pytest.raises(InvalidParameterError):
            client.write_events([
                TestWriteSubjects.test_source.new_event(
                    subject='',
                    event_type='com.foo.bar',
                    data={}
                )
            ])

    @staticmethod
    def test_throws_an_error_for_malformed_type():
        client = TestWriteSubjects.database.without_authorization.client

        with pytest.raises(InvalidParameterError):
            client.write_events([
                TestWriteSubjects.test_source.new_event(
                    subject='/',
                    event_type='',
                    data={}
                )
            ])

    @staticmethod
    def test_supports_authorization():
        client = TestWriteSubjects.database.with_authorization.client

        client.write_events([
            TestWriteSubjects.test_source.new_event(
                subject='/',
                event_type='com.foo.bar',
                data={}
            )
        ])


class TestWriteEventsWithMockServer:
    stop_server: StopServer = lambda: None
    test_source = Source(TEST_SOURCE)
    events = [test_source.new_event('/', 'com.foo.bar', {})]

    @staticmethod
    def teardown_method():
        TestWriteEventsWithMockServer.stop_server()

    @staticmethod
    def test_throws_error_if_server_responds_with_5xx_status_code():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_write_events(response: Response) -> Response:
                response.status_code = HTTPStatus.BAD_GATEWAY
                response.set_data(HTTPStatus.BAD_GATEWAY.phrase)
                return response

            attach_handler('/api/write-events', 'POST', handle_write_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestWriteEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ServerError):
            for _ in client.write_events(TestWriteEventsWithMockServer.events):
                pass

    @staticmethod
    def test_throws_error_if_protocol_version_does_not_match():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_write_events(response: Response) -> Response:
                response.headers['X-EventSourcingDB-Protocol-Version'] = '0.0.0'
                response.status_code = HTTPStatus.UNPROCESSABLE_ENTITY
                response.set_data(HTTPStatus.UNPROCESSABLE_ENTITY.phrase)
                return response

            attach_handler('/api/write-events', 'POST', handle_write_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestWriteEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ClientError):
            for _ in client.write_events(TestWriteEventsWithMockServer.events):
                pass

    @staticmethod
    def test_throws_error_if_server_responds_with_4xx_status_code():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_write_events(response: Response) -> Response:
                response.status_code = HTTPStatus.NOT_FOUND
                response.set_data(HTTPStatus.NOT_FOUND.phrase)
                return response

            attach_handler('/api/write-events', 'POST', handle_write_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestWriteEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ClientError):
            for _ in client.write_events(TestWriteEventsWithMockServer.events):
                pass

    @staticmethod
    def test_throws_error_if_server_responds_with_unexpected_status_code():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_write_events(response: Response) -> Response:
                response.status_code = HTTPStatus.ACCEPTED
                response.set_data(HTTPStatus.ACCEPTED.phrase)
                return response

            attach_handler('/api/write-events', 'POST', handle_write_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestWriteEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ServerError):
            for _ in client.write_events(TestWriteEventsWithMockServer.events):
                pass

    @staticmethod
    def test_throws_error_if_response_cannot_be_parsed():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_write_events(response: Response) -> Response:
                response.set_data('this is not data')
                return response

            attach_handler('/api/write-events', 'POST', handle_write_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestWriteEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ServerError):
            for _ in client.write_events(TestWriteEventsWithMockServer.events):
                pass
