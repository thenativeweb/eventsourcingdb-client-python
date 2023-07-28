from http import HTTPStatus

import pytest

from eventsourcingdb_client_python.errors.client_error import ClientError
from eventsourcingdb_client_python.errors.invalid_parameter_error import InvalidParameterError
from eventsourcingdb_client_python.errors.server_error import ServerError
from eventsourcingdb_client_python.event.source import Source
from eventsourcingdb_client_python.handlers.observe_events import \
    ObserveEventsOptions, \
    ObserveFromLatestEvent, \
    IfEventIsMissingDuringObserve

from .shared.event.assert_event import assert_event
from .shared.build_database import build_database
from .shared.database import Database
from .shared.event.test_source import TEST_SOURCE
from .shared.start_local_http_server import \
    StopServer,\
    AttachHandler,\
    Response,\
    start_local_http_server
from .shared.tracing import new_tracing_context


class TestObserveEvents:
    database: Database
    source = Source(TEST_SOURCE)
    REGISTERED_SUBJECT = '/users/registered'
    LOGGED_IN_SUBJECT = '/users/loggedIn'
    REGISTERED_TYPE = 'io.thenativeweb.users.registered'
    LOGGED_IN_TYPE = 'io.thenativeweb.users.loggedIn'
    JANE_DATA = {'name': 'jane'}
    JOHN_DATA = {'name': 'john'}
    APFEL_FRED_DATA = {'name': 'apfel fred'}
    TRACING_CONTEXT_1 = new_tracing_context("10000000000000000000000000000000", "1000000000000000")
    TRACING_CONTEXT_2 = new_tracing_context("20000000000000000000000000000000", "2000000000000000")
    TRACING_CONTEXT_3 = new_tracing_context("30000000000000000000000000000000", "3000000000000000")
    TRACING_CONTEXT_4 = new_tracing_context("40000000000000000000000000000000", "4000000000000000")
    TRACING_CONTEXT_5 = new_tracing_context("50000000000000000000000000000000", "5000000000000000")

    @classmethod
    def setup_class(cls):
        build_database('tests/shared/docker/eventsourcingdb')

    @staticmethod
    def setup_method():
        TestObserveEvents.database = Database()

        database = TestObserveEvents.database.with_authorization
        database.client.write_events([
            TestObserveEvents.source.new_event(
                TestObserveEvents.REGISTERED_SUBJECT,
                TestObserveEvents.REGISTERED_TYPE,
                TestObserveEvents.JANE_DATA,
                TestObserveEvents.TRACING_CONTEXT_1
            ),
            TestObserveEvents.source.new_event(
                TestObserveEvents.LOGGED_IN_SUBJECT,
                TestObserveEvents.LOGGED_IN_TYPE,
                TestObserveEvents.JANE_DATA,
                TestObserveEvents.TRACING_CONTEXT_2
            ),
            TestObserveEvents.source.new_event(
                TestObserveEvents.REGISTERED_SUBJECT,
                TestObserveEvents.REGISTERED_TYPE,
                TestObserveEvents.JOHN_DATA,
                TestObserveEvents.TRACING_CONTEXT_3
            ),
            TestObserveEvents.source.new_event(
                TestObserveEvents.LOGGED_IN_SUBJECT,
                TestObserveEvents.LOGGED_IN_TYPE,
                TestObserveEvents.JOHN_DATA,
                TestObserveEvents.TRACING_CONTEXT_4
            ),
        ])

    @staticmethod
    def teardown_method():
        TestObserveEvents.registered_count = 0
        TestObserveEvents.logged_in_count = 0
        TestObserveEvents.database.stop()

    @staticmethod
    def test_throws_error_if_server_is_not_reachable():
        client = TestObserveEvents.database.with_invalid_url.client

        with pytest.raises(ServerError):
            for _ in client.observe_events('/', ObserveEventsOptions(recursive=False)):
                pass

    @staticmethod
    def test_throws_error_if_subject_is_invalid():
        client = TestObserveEvents.database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            for _ in client.observe_events('', ObserveEventsOptions(recursive=False)):
                pass

    @staticmethod
    def test_supports_authorization():
        client = TestObserveEvents.database.with_authorization.client

        observed_items_count = 0
        for _ in client.observe_events('/', ObserveEventsOptions(recursive=True)):
            observed_items_count += 1

            total_store_items_count = 4
            if observed_items_count == total_store_items_count:
                return

    @staticmethod
    def test_observes_event_from_a_single_subject():
        client = TestObserveEvents.database.with_authorization.client
        observed_items = []
        did_push_intermediate_event = False

        for event in client.observe_events(
            TestObserveEvents.REGISTERED_SUBJECT,
            ObserveEventsOptions(recursive=False)
        ):
            observed_items.append(event)

            if not did_push_intermediate_event:
                client.write_events([TestObserveEvents.source.new_event(
                    subject=TestObserveEvents.REGISTERED_SUBJECT,
                    event_type=TestObserveEvents.REGISTERED_TYPE,
                    data=TestObserveEvents.APFEL_FRED_DATA,
                    tracing_context=TestObserveEvents.TRACING_CONTEXT_5
                )])

                did_push_intermediate_event = True

            registered_events_count = 3
            if len(observed_items) == registered_events_count:
                break

        assert_event(
            observed_items[0].event,
            TEST_SOURCE,
            TestObserveEvents.REGISTERED_SUBJECT,
            TestObserveEvents.REGISTERED_TYPE,
            TestObserveEvents.JANE_DATA,
            TestObserveEvents.TRACING_CONTEXT_1
        )
        assert_event(
            observed_items[1].event,
            TEST_SOURCE,
            TestObserveEvents.REGISTERED_SUBJECT,
            TestObserveEvents.REGISTERED_TYPE,
            TestObserveEvents.JOHN_DATA,
            TestObserveEvents.TRACING_CONTEXT_3
        )
        assert_event(
            observed_items[2].event,
            TEST_SOURCE,
            TestObserveEvents.REGISTERED_SUBJECT,
            TestObserveEvents.REGISTERED_TYPE,
            TestObserveEvents.APFEL_FRED_DATA,
            TestObserveEvents.TRACING_CONTEXT_5
        )

    @staticmethod
    def test_observes_event_from_a_subject_including_child_subjects():
        client = TestObserveEvents.database.with_authorization.client
        observed_items = []
        did_push_intermediate_event = False

        for event in client.observe_events(
            '/users',
            ObserveEventsOptions(recursive=True)
        ):
            observed_items.append(event)

            if not did_push_intermediate_event:
                client.write_events([TestObserveEvents.source.new_event(
                    subject=TestObserveEvents.REGISTERED_SUBJECT,
                    event_type=TestObserveEvents.REGISTERED_TYPE,
                    data=TestObserveEvents.APFEL_FRED_DATA,
                    tracing_context=TestObserveEvents.TRACING_CONTEXT_5
                )])

                did_push_intermediate_event = True

            total_events_count = 5
            if len(observed_items) == total_events_count:
                break

        assert_event(
            observed_items[0].event,
            TEST_SOURCE,
            TestObserveEvents.REGISTERED_SUBJECT,
            TestObserveEvents.REGISTERED_TYPE,
            TestObserveEvents.JANE_DATA,
            TestObserveEvents.TRACING_CONTEXT_1
        )
        assert_event(
            observed_items[1].event,
            TEST_SOURCE,
            TestObserveEvents.LOGGED_IN_SUBJECT,
            TestObserveEvents.LOGGED_IN_TYPE,
            TestObserveEvents.JANE_DATA,
            TestObserveEvents.TRACING_CONTEXT_2
        )
        assert_event(
            observed_items[2].event,
            TEST_SOURCE,
            TestObserveEvents.REGISTERED_SUBJECT,
            TestObserveEvents.REGISTERED_TYPE,
            TestObserveEvents.JOHN_DATA,
            TestObserveEvents.TRACING_CONTEXT_3
        )
        assert_event(
            observed_items[3].event,
            TEST_SOURCE,
            TestObserveEvents.LOGGED_IN_SUBJECT,
            TestObserveEvents.LOGGED_IN_TYPE,
            TestObserveEvents.JOHN_DATA,
            TestObserveEvents.TRACING_CONTEXT_4
        )
        assert_event(
            observed_items[4].event,
            TEST_SOURCE,
            TestObserveEvents.REGISTERED_SUBJECT,
            TestObserveEvents.REGISTERED_TYPE,
            TestObserveEvents.APFEL_FRED_DATA,
            TestObserveEvents.TRACING_CONTEXT_5
        )

    @staticmethod
    def test_observes_event_starting_from_given_event_name():
        client = TestObserveEvents.database.with_authorization.client
        observed_items = []
        did_push_intermediate_event = False

        for event in client.observe_events(
            '/users',
            ObserveEventsOptions(
                recursive=True,
                from_latest_event=ObserveFromLatestEvent(
                    subject=TestObserveEvents.LOGGED_IN_SUBJECT,
                    type=TestObserveEvents.LOGGED_IN_TYPE,
                    if_event_is_missing=IfEventIsMissingDuringObserve.READ_EVERYTHING
                )
            )
        ):
            observed_items.append(event)

            if not did_push_intermediate_event:
                client.write_events([TestObserveEvents.source.new_event(
                    subject=TestObserveEvents.REGISTERED_SUBJECT,
                    event_type=TestObserveEvents.REGISTERED_TYPE,
                    data=TestObserveEvents.APFEL_FRED_DATA,
                    tracing_context=TestObserveEvents.TRACING_CONTEXT_5
                )])

                did_push_intermediate_event = True

            event_count_after_last_login = 2
            if len(observed_items) == event_count_after_last_login:
                break

        assert_event(
            observed_items[0].event,
            TEST_SOURCE,
            TestObserveEvents.LOGGED_IN_SUBJECT,
            TestObserveEvents.LOGGED_IN_TYPE,
            TestObserveEvents.JOHN_DATA,
            TestObserveEvents.TRACING_CONTEXT_4
        )
        assert_event(
            observed_items[1].event,
            TEST_SOURCE,
            TestObserveEvents.REGISTERED_SUBJECT,
            TestObserveEvents.REGISTERED_TYPE,
            TestObserveEvents.APFEL_FRED_DATA,
            TestObserveEvents.TRACING_CONTEXT_5
        )

    @staticmethod
    def test_observes_event_starting_from_given_lower_bound_id():
        client = TestObserveEvents.database.with_authorization.client
        observed_items = []
        did_push_intermediate_event = False

        for event in client.observe_events(
            '/users',
            ObserveEventsOptions(
                recursive=True,
                lower_bound_id='2'
            )
        ):
            observed_items.append(event)

            if not did_push_intermediate_event:
                client.write_events([TestObserveEvents.source.new_event(
                    subject=TestObserveEvents.REGISTERED_SUBJECT,
                    event_type=TestObserveEvents.REGISTERED_TYPE,
                    data=TestObserveEvents.APFEL_FRED_DATA,
                    tracing_context=TestObserveEvents.TRACING_CONTEXT_5
                )])

                did_push_intermediate_event = True

            event_count_after_given_id = 3
            if len(observed_items) == event_count_after_given_id:
                break

        assert_event(
            observed_items[0].event,
            TEST_SOURCE,
            TestObserveEvents.REGISTERED_SUBJECT,
            TestObserveEvents.REGISTERED_TYPE,
            TestObserveEvents.JOHN_DATA,
            TestObserveEvents.TRACING_CONTEXT_3
        )
        assert_event(
            observed_items[1].event,
            TEST_SOURCE,
            TestObserveEvents.LOGGED_IN_SUBJECT,
            TestObserveEvents.LOGGED_IN_TYPE,
            TestObserveEvents.JOHN_DATA,
            TestObserveEvents.TRACING_CONTEXT_4
        )
        assert_event(
            observed_items[2].event,
            TEST_SOURCE,
            TestObserveEvents.REGISTERED_SUBJECT,
            TestObserveEvents.REGISTERED_TYPE,
            TestObserveEvents.APFEL_FRED_DATA,
            TestObserveEvents.TRACING_CONTEXT_5
        )

    @staticmethod
    def test_throws_error_for_mutually_exclusive_options():
        client = TestObserveEvents.database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            for _ in client.observe_events(
                '/users',
                ObserveEventsOptions(
                    recursive=True,
                    lower_bound_id='3',
                    from_latest_event=ObserveFromLatestEvent(
                        subject='/',
                        type='com.foo.bar',
                        if_event_is_missing=IfEventIsMissingDuringObserve.READ_EVERYTHING
                    )
                )
            ):
                pass

    @staticmethod
    def test_throws_error_for_non_integer_lower_bound():
        client = TestObserveEvents.database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            for _ in client.observe_events(
                '/users',
                ObserveEventsOptions(
                    recursive=True,
                    lower_bound_id='hello',
                )
            ):
                pass

    @staticmethod
    def test_throws_error_for_negative_lower_bound():
        client = TestObserveEvents.database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            for _ in client.observe_events(
                '/users',
                ObserveEventsOptions(
                    recursive=True,
                    lower_bound_id='-1',
                )
            ):
                pass

    @staticmethod
    def test_throws_error_for_invalid_subject_in_from_latest_event():
        client = TestObserveEvents.database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            for _ in client.observe_events(
                '/users',
                ObserveEventsOptions(
                    recursive=True,
                    from_latest_event=ObserveFromLatestEvent(
                        subject='',
                        type='com.foo.bar',
                        if_event_is_missing=IfEventIsMissingDuringObserve.READ_EVERYTHING
                    )
                )
            ):
                pass

    @staticmethod
    def test_throws_error_for_invalid_type_in_from_latest_event():
        client = TestObserveEvents.database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            for _ in client.observe_events(
                '/users',
                ObserveEventsOptions(
                    recursive=True,
                    from_latest_event=ObserveFromLatestEvent(
                        subject='/',
                        type='',
                        if_event_is_missing=IfEventIsMissingDuringObserve.READ_EVERYTHING
                    )
                )
            ):
                pass

class TestObserveEventsWithMockServer:
    stop_server: StopServer = lambda: None

    @staticmethod
    def teardown_method():
        TestObserveEventsWithMockServer.stop_server()

    @staticmethod
    def test_throws_error_if_server_responds_with_5xx_status_code():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_observe_events(response: Response) -> Response:
                response.status_code = HTTPStatus.BAD_GATEWAY
                response.set_data(HTTPStatus.BAD_GATEWAY.phrase)
                return response

            attach_handler('/api/observe-events', 'POST', handle_observe_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestObserveEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ServerError):
            for _ in client.observe_events(
                subject='/',
                options=ObserveEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    def test_throws_error_if_protocol_version_does_not_match():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_observe_events(response: Response) -> Response:
                response.headers['X-EventSourcingDB-Protocol-Version'] = '0.0.0'
                response.status_code = HTTPStatus.UNPROCESSABLE_ENTITY
                response.set_data(HTTPStatus.UNPROCESSABLE_ENTITY.phrase)
                return response

            attach_handler('/api/observe-events', 'POST', handle_observe_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestObserveEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ClientError):
            for _ in client.observe_events(
                '/',
                ObserveEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    def test_throws_error_if_server_responds_with_4xx_status_code():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_observe_events(response: Response) -> Response:
                response.status_code = HTTPStatus.NOT_FOUND
                response.set_data(HTTPStatus.NOT_FOUND.phrase)
                return response

            attach_handler('/api/observe-events', 'POST', handle_observe_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestObserveEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ClientError):
            for _ in client.observe_events(
                '/',
                ObserveEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    def test_throws_error_if_server_responds_with_unexpected_status_code():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_observe_events(response: Response) -> Response:
                response.status_code = HTTPStatus.ACCEPTED
                response.set_data(HTTPStatus.ACCEPTED.phrase)
                return response

            attach_handler('/api/observe-events', 'POST', handle_observe_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestObserveEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ServerError):
            for _ in client.observe_events(
                '/',
                ObserveEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    def test_throws_error_if_server_responds_with_an_item_that_cannot_be_parsed():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_observe_events(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('cannot be parsed')
                return response

            attach_handler('/api/observe-events', 'POST', handle_observe_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestObserveEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ServerError):
            for _ in client.observe_events(
                '/',
                ObserveEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    def test_throws_error_if_server_responds_with_an_item_that_has_an_unexpected_type():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_observe_events(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('{"type": "clown", "payload": {"foo": "bar"}}')
                return response

            attach_handler('/api/observe-events', 'POST', handle_observe_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestObserveEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ServerError):
            for _ in client.observe_events(
                '/',
                ObserveEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    def test_throws_error_if_server_responds_with_an_error_item():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_observe_events(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('{"type": "error", "payload": {"error": "it is just broken"}}')
                return response

            attach_handler('/api/observe-events', 'POST', handle_observe_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestObserveEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ServerError):
            for _ in client.observe_events(
                '/',
                ObserveEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    def test_throws_error_if_server_responds_with_an_error_item_with_unexpected_payload():
        def attach_handlers(attach_handler: AttachHandler):
            def handle_observe_events(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('{"type": "error", "payload": {"not very correct": "indeed"}}')
                return response

            attach_handler('/api/observe-events', 'POST', handle_observe_events)

        client, stop_server = start_local_http_server(attach_handlers)
        TestObserveEventsWithMockServer.stop_server = stop_server

        with pytest.raises(ServerError):
            for _ in client.observe_events(
                '/',
                ObserveEventsOptions(
                    recursive=True
                )
            ):
                pass
