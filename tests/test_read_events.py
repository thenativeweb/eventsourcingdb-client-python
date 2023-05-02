from http import HTTPStatus

import pytest

from eventsourcingdb_client_python.errors.client_error import ClientError
from eventsourcingdb_client_python.errors.invalid_parameter_error import InvalidParameterError
from eventsourcingdb_client_python.errors.server_error import ServerError
from eventsourcingdb_client_python.event.source import Source
from eventsourcingdb_client_python.handlers.read_events import \
    ReadEventsOptions, \
    ReadFromLatestEvent, \
    IfEventIsMissing
from eventsourcingdb_client_python.handlers.read_events.order import Order

from .shared.build_database import build_database
from .shared.database import Database
from .shared.event.assert_event import assert_event
from .shared.event.test_source import TEST_SOURCE
from .shared.start_local_http_server import \
    StopServer,\
    AttachHandler,\
    start_local_http_server,\
    Response


class TestReadEvents:
    database: Database
    source = Source(TEST_SOURCE)
    REGISTERED_SUBJECT = '/users/registered'
    LOGGED_IN_SUBJECT = '/users/loggedIn'
    REGISTERED_TYPE = 'io.thenativeweb.users.registered'
    LOGGED_IN_TYPE = 'io.thenativeweb.users.loggedIn'
    JANE_DATA = {'name': 'jane'}
    JOHN_DATA = {'name': 'john'}


    @classmethod
    def setup_class(cls):
        build_database('tests/shared/docker/eventsourcingdb')

    @staticmethod
    def setup_method():
        TestReadEvents.database = Database()

        TestReadEvents.database.without_authorization.client.write_events([
            TestReadEvents.source.new_event(
                TestReadEvents.REGISTERED_SUBJECT,
                TestReadEvents.REGISTERED_TYPE,
                TestReadEvents.JANE_DATA
            ),
            TestReadEvents.source.new_event(
                TestReadEvents.LOGGED_IN_SUBJECT,
                TestReadEvents.LOGGED_IN_TYPE,
                TestReadEvents.JANE_DATA
            ),
            TestReadEvents.source.new_event(
                TestReadEvents.REGISTERED_SUBJECT,
                TestReadEvents.REGISTERED_TYPE,
                TestReadEvents.JOHN_DATA
            ),
            TestReadEvents.source.new_event(
                TestReadEvents.LOGGED_IN_SUBJECT,
                TestReadEvents.LOGGED_IN_TYPE,
                TestReadEvents.JOHN_DATA
            ),
        ])

    @staticmethod
    def teardown_method():
        TestReadEvents.registered_count = 0
        TestReadEvents.logged_in_count = 0
        TestReadEvents.database.stop()

    @staticmethod
    def test_throws_error_if_server_is_not_reachable():
        client = TestReadEvents.database.with_invalid_url.client

        with pytest.raises(ServerError):
            for _ in client.read_events('/', ReadEventsOptions(recursive=False)):
                pass

    @staticmethod
    def test_supports_authorization():
        client = TestReadEvents.database.with_authorization.client

        for _ in client.read_events('/', ReadEventsOptions(recursive=False)):
            pass

    @staticmethod
    def test_read_events_from_a_single_subject():
        client = TestReadEvents.database.without_authorization.client

        result = []
        for event in client.read_events(
            TestReadEvents.REGISTERED_SUBJECT,
            ReadEventsOptions(recursive=False)
        ):
            result.append(event)

        registered_count = 2
        assert len(result) == registered_count
        assert_event(
            result[0].event,
            TEST_SOURCE,
            TestReadEvents.REGISTERED_SUBJECT,
            TestReadEvents.REGISTERED_TYPE,
            TestReadEvents.JANE_DATA
        )
        assert result[1].event.source == TEST_SOURCE
        assert result[1].event.subject == TestReadEvents.REGISTERED_SUBJECT
        assert result[1].event.type == TestReadEvents.REGISTERED_TYPE

    @staticmethod
    def test_read_events_from_a_subject_including_children():
        client = TestReadEvents.database.without_authorization.client

        result = []
        for event in client.read_events(
            '/users',
            ReadEventsOptions(recursive=True)
        ):
            result.append(event)

        total_event_count = 4
        assert len(result) == total_event_count
        assert result[0].event.source == TEST_SOURCE
        assert result[0].event.subject == TestReadEvents.REGISTERED_SUBJECT
        assert result[0].event.type == TestReadEvents.REGISTERED_TYPE
        assert result[0].event.data == TestReadEvents.JANE_DATA
        assert result[1].event.source == TEST_SOURCE
        assert result[1].event.subject == TestReadEvents.LOGGED_IN_SUBJECT
        assert result[1].event.type == TestReadEvents.LOGGED_IN_TYPE
        assert result[1].event.data == TestReadEvents.JANE_DATA
        assert result[2].event.source == TEST_SOURCE
        assert result[2].event.subject == TestReadEvents.REGISTERED_SUBJECT
        assert result[2].event.type == TestReadEvents.REGISTERED_TYPE
        assert result[2].event.data == TestReadEvents.JOHN_DATA
        assert result[3].event.source == TEST_SOURCE
        assert result[3].event.subject == TestReadEvents.LOGGED_IN_SUBJECT
        assert result[3].event.type == TestReadEvents.LOGGED_IN_TYPE
        assert result[3].event.data == TestReadEvents.JOHN_DATA

    @staticmethod
    def test_read_events_in_antichronological_order():
        client = TestReadEvents.database.without_authorization.client

        result = []
        for event in client.read_events(
            TestReadEvents.REGISTERED_SUBJECT,
            ReadEventsOptions(recursive=False, order=Order.ANTICHRONOLOGICAL)
        ):
            result.append(event)

        registered_count = 2
        assert len(result) == registered_count
        assert result[0].event.source == TEST_SOURCE
        assert result[0].event.subject == TestReadEvents.REGISTERED_SUBJECT
        assert result[0].event.type == TestReadEvents.REGISTERED_TYPE
        assert result[0].event.data == TestReadEvents.JOHN_DATA
        assert result[1].event.source == TEST_SOURCE
        assert result[1].event.subject == TestReadEvents.REGISTERED_SUBJECT
        assert result[1].event.type == TestReadEvents.REGISTERED_TYPE
        assert result[1].event.data == TestReadEvents.JANE_DATA

    @staticmethod
    def test_read_events_matching_event_names():
        client = TestReadEvents.database.without_authorization.client

        result = []
        for event in client.read_events(
            '/users',
            ReadEventsOptions(
                recursive=True,
                from_latest_event=ReadFromLatestEvent(
                    subject=TestReadEvents.REGISTERED_SUBJECT,
                    type=TestReadEvents.REGISTERED_TYPE,
                    if_event_is_missing=IfEventIsMissing.READ_EVERYTHING
                )
            )
        ):
            result.append(event)

        john_count = 2
        assert len(result) == john_count
        assert result[0].event.source == TEST_SOURCE
        assert result[0].event.subject == TestReadEvents.REGISTERED_SUBJECT
        assert result[0].event.type == TestReadEvents.REGISTERED_TYPE
        assert result[0].event.data == TestReadEvents.JOHN_DATA
        assert result[1].event.source == TEST_SOURCE
        assert result[1].event.subject == TestReadEvents.LOGGED_IN_SUBJECT
        assert result[1].event.type == TestReadEvents.LOGGED_IN_TYPE
        assert result[1].event.data == TestReadEvents.JOHN_DATA

    @staticmethod
    def test_read_events_starting_from_lower_bound_id():
        client = TestReadEvents.database.without_authorization.client

        result = []
        for event in client.read_events(
            '/users',
            ReadEventsOptions(
                recursive=True,
                lower_bound_id='2'
            )
        ):
            result.append(event)

        john_count = 2
        assert len(result) == john_count
        assert result[0].event.source == TEST_SOURCE
        assert result[0].event.subject == TestReadEvents.REGISTERED_SUBJECT
        assert result[0].event.type == TestReadEvents.REGISTERED_TYPE
        assert result[0].event.data == TestReadEvents.JOHN_DATA
        assert result[1].event.source == TEST_SOURCE
        assert result[1].event.subject == TestReadEvents.LOGGED_IN_SUBJECT
        assert result[1].event.type == TestReadEvents.LOGGED_IN_TYPE
        assert result[1].event.data == TestReadEvents.JOHN_DATA

    @staticmethod
    def test_read_events_up_to_the_upper_bound_id():
        client = TestReadEvents.database.without_authorization.client

        result = []
        for event in client.read_events(
            '/users',
            ReadEventsOptions(
                recursive=True,
                upper_bound_id='1'
            )
        ):
            result.append(event)

        jane_count = 2
        assert len(result) == jane_count
        assert result[0].event.source == TEST_SOURCE
        assert result[0].event.subject == TestReadEvents.REGISTERED_SUBJECT
        assert result[0].event.type == TestReadEvents.REGISTERED_TYPE
        assert result[0].event.data == TestReadEvents.JANE_DATA
        assert result[1].event.source == TEST_SOURCE
        assert result[1].event.subject == TestReadEvents.LOGGED_IN_SUBJECT
        assert result[1].event.type == TestReadEvents.LOGGED_IN_TYPE
        assert result[1].event.data == TestReadEvents.JANE_DATA

    @staticmethod
    def test_throws_error_for_exclusive_options():
        client = TestReadEvents.database.without_authorization.client

        with pytest.raises(InvalidParameterError):
            for _ in client.read_events(
                '/users',
                ReadEventsOptions(
                    recursive=True,
                    from_latest_event=ReadFromLatestEvent(
                        subject='/',
                        type='com.foo.bar',
                        if_event_is_missing=IfEventIsMissing.READ_EVERYTHING
                    ),
                    lower_bound_id='0'
                )
            ):
                pass

    @staticmethod
    def test_throws_error_for_invalid_subject():
        client = TestReadEvents.database.without_authorization.client

        with pytest.raises(InvalidParameterError):
            for _ in client.read_events(
                '',
                ReadEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    def test_throws_error_for_invalid_lower_bound_id():
        client = TestReadEvents.database.without_authorization.client

        with pytest.raises(InvalidParameterError):
            for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    lower_bound_id='hello'
                )
            ):
                pass

    @staticmethod
    def test_throws_error_for_negative_lower_bound_id():
        client = TestReadEvents.database.without_authorization.client

        with pytest.raises(InvalidParameterError):
            for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    lower_bound_id='-1'
                )
            ):
                pass

    @staticmethod
    def test_throws_error_for_invalid_upper_bound_id():
        client = TestReadEvents.database.without_authorization.client

        with pytest.raises(InvalidParameterError):
            for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    upper_bound_id='hello'
                )
            ):
                pass

    @staticmethod
    def test_throws_error_for_negative_upper_bound_id():
        client = TestReadEvents.database.without_authorization.client

        with pytest.raises(InvalidParameterError):
            for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    upper_bound_id='-1'
                )
            ):
                pass

    @staticmethod
    def test_throws_error_for_invalid_subject_in_from_latest_event():
        client = TestReadEvents.database.without_authorization.client

        with pytest.raises(InvalidParameterError):
            for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    from_latest_event=ReadFromLatestEvent(
                        subject='',
                        type='com.foo.bar',
                        if_event_is_missing=IfEventIsMissing.READ_EVERYTHING
                    )
                )
            ):
                pass

    @staticmethod
    def test_throws_error_for_invalid_type_in_from_latest_event():
        client = TestReadEvents.database.without_authorization.client

        with pytest.raises(InvalidParameterError):
            for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    from_latest_event=ReadFromLatestEvent(
                        subject='/',
                        type='',
                        if_event_is_missing=IfEventIsMissing.READ_EVERYTHING
                    )
                )
            ):
                pass


class TestReadEventsWithMockServer:
    stop_server: StopServer = lambda: None

    @staticmethod
    def teardown_method():
        TestReadEventsWithMockServer.stop_server()

    @staticmethod
    def test_throws_error_if_server_responds_with_5xx_status_code():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_events(response: Response) -> Response:
                response.status_code = HTTPStatus.BAD_GATEWAY
                response.set_data(HTTPStatus.BAD_GATEWAY.phrase)
                return response

            attach_handler('/api/read-events', 'POST', handle_read_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestReadEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ServerError):
            for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    def test_throws_error_if_protocol_version_does_not_match():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_events(response: Response) -> Response:
                response.headers['X-EventSourcingDB-Protocol-Version'] = '0.0.0'
                response.status_code = HTTPStatus.UNPROCESSABLE_ENTITY
                response.set_data(HTTPStatus.UNPROCESSABLE_ENTITY.phrase)
                return response

            attach_handler('/api/read-events', 'POST', handle_read_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestReadEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ClientError):
            for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    def test_throws_error_if_server_responds_with_4xx_status_code():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_events(response: Response) -> Response:
                response.status_code = HTTPStatus.NOT_FOUND
                response.set_data(HTTPStatus.NOT_FOUND.phrase)
                return response

            attach_handler('/api/read-events', 'POST', handle_read_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestReadEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ClientError):
            for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    def test_throws_error_if_server_responds_with_unexpected_status_code():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_events(response: Response) -> Response:
                response.status_code = HTTPStatus.ACCEPTED
                response.set_data(HTTPStatus.ACCEPTED.phrase)
                return response

            attach_handler('/api/read-events', 'POST', handle_read_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestReadEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ServerError):
            for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    def test_throws_error_if_server_responds_with_an_item_that_cannot_be_parsed():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_events(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('cannot be parsed')
                return response

            attach_handler('/api/read-events', 'POST', handle_read_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestReadEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ServerError):
            for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    def test_throws_error_if_server_responds_with_an_item_that_has_an_unexpected_type():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_events(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('{"type": "clown", "payload": {"foo": "bar"}}')
                return response

            attach_handler('/api/read-events', 'POST', handle_read_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestReadEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ServerError):
            for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    def test_throws_error_if_server_responds_with_an_error_item():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_events(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('{"type": "error", "payload": {"error": "it is just broken"}}')
                return response

            attach_handler('/api/read-events', 'POST', handle_read_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestReadEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ServerError):
            for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    def test_throws_error_if_server_responds_with_an_error_item_with_unexpected_payload():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_events(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('{"type": "error", "payload": {"not very correct": "indeed"}}')
                return response

            attach_handler('/api/read-events', 'POST', handle_read_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestReadEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ServerError):
            for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True
                )
            ):
                pass
