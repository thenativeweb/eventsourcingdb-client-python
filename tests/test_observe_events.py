from collections.abc import Awaitable, Callable
from http import HTTPStatus

import pytest
import pytest_asyncio

from eventsourcingdb_client_python.client import Client
from eventsourcingdb_client_python.errors.client_error import ClientError
from eventsourcingdb_client_python.errors.invalid_parameter_error import InvalidParameterError
from eventsourcingdb_client_python.errors.server_error import ServerError
from eventsourcingdb_client_python.event.source import Source
from eventsourcingdb_client_python.handlers.observe_events import \
    ObserveEventsOptions, \
    ObserveFromLatestEvent, \
    IfEventIsMissingDuringObserve

from .shared.build_database import build_database
from .shared.database import Database
from .shared.event.test_source import TEST_SOURCE
from .shared.start_local_http_server import \
    StopServer, \
    AttachHandler, \
    Response, \
    start_local_http_server, AttachHandlers


@pytest_asyncio.fixture
async def prepared_database(database: Database) -> Database:
    await database.with_authorization.client.write_events([
        TestObserveEvents.source.new_event(
            TestObserveEvents.REGISTERED_SUBJECT,
            TestObserveEvents.REGISTERED_TYPE,
            TestObserveEvents.JANE_DATA
        ),
        TestObserveEvents.source.new_event(
            TestObserveEvents.LOGGED_IN_SUBJECT,
            TestObserveEvents.LOGGED_IN_TYPE,
            TestObserveEvents.JANE_DATA
        ),
        TestObserveEvents.source.new_event(
            TestObserveEvents.REGISTERED_SUBJECT,
            TestObserveEvents.REGISTERED_TYPE,
            TestObserveEvents.JOHN_DATA
        ),
        TestObserveEvents.source.new_event(
            TestObserveEvents.LOGGED_IN_SUBJECT,
            TestObserveEvents.LOGGED_IN_TYPE,
            TestObserveEvents.JOHN_DATA
        ),
    ])

    return database


class TestObserveEvents:
    source = Source(TEST_SOURCE)
    REGISTERED_SUBJECT = '/users/registered'
    LOGGED_IN_SUBJECT = '/users/loggedIn'
    REGISTERED_TYPE = 'io.thenativeweb.users.registered'
    LOGGED_IN_TYPE = 'io.thenativeweb.users.loggedIn'
    JANE_DATA = {'name': 'jane'}
    JOHN_DATA = {'name': 'john'}
    APFEL_FRED_DATA = {'name': 'apfel fred'}

    @classmethod
    def setup_class(cls):
        build_database('tests/shared/docker/eventsourcingdb')

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_is_not_reachable(
        database: Database
    ):
        client = database.with_invalid_url.client

        with pytest.raises(ServerError):
            async for _ in client.observe_events('/', ObserveEventsOptions(recursive=False)):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_subject_is_invalid(
        database: Database
    ):
        client = database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            async for _ in client.observe_events('', ObserveEventsOptions(recursive=False)):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_supports_authorization(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        observed_items_count = 0
        events = client.observe_events('/', ObserveEventsOptions(recursive=True))
        async for _ in events:
            observed_items_count += 1

            total_store_items_count = 4
            if observed_items_count == total_store_items_count:
                break

    @staticmethod
    @pytest.mark.asyncio
    async def test_observes_event_from_a_single_subject(
         prepared_database: Database
     ):
        client = prepared_database.with_authorization.client
        registered_events_count = 3

        observed_items = []

        events = client.observe_events(
            TestObserveEvents.REGISTERED_SUBJECT,
            ObserveEventsOptions(recursive=False)
        )

        await client.write_events([TestObserveEvents.source.new_event(
            subject=TestObserveEvents.REGISTERED_SUBJECT,
            event_type=TestObserveEvents.REGISTERED_TYPE,
            data=TestObserveEvents.APFEL_FRED_DATA
        )])

        async for event in events:
            observed_items.append(event)

            if len(observed_items) == registered_events_count:
                break

        assert observed_items[0].event.source == TEST_SOURCE
        assert observed_items[0].event.subject == TestObserveEvents.REGISTERED_SUBJECT
        assert observed_items[0].event.type == TestObserveEvents.REGISTERED_TYPE
        assert observed_items[0].event.data == TestObserveEvents.JANE_DATA
        assert observed_items[1].event.source == TEST_SOURCE
        assert observed_items[1].event.subject == TestObserveEvents.REGISTERED_SUBJECT
        assert observed_items[1].event.type == TestObserveEvents.REGISTERED_TYPE
        assert observed_items[1].event.data == TestObserveEvents.JOHN_DATA
        assert observed_items[2].event.source == TEST_SOURCE
        assert observed_items[2].event.subject == TestObserveEvents.REGISTERED_SUBJECT
        assert observed_items[2].event.type == TestObserveEvents.REGISTERED_TYPE
        assert observed_items[2].event.data == TestObserveEvents.APFEL_FRED_DATA

    @staticmethod
    @pytest.mark.asyncio
    async def test_observes_event_from_a_subject_including_child_subjects(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client
        observed_items = []
        did_push_intermediate_event = False

        async for event in client.observe_events(
            '/users',
            ObserveEventsOptions(recursive=True)
        ):
            observed_items.append(event)

            if not did_push_intermediate_event:
                await client.write_events([TestObserveEvents.source.new_event(
                    subject=TestObserveEvents.REGISTERED_SUBJECT,
                    event_type=TestObserveEvents.REGISTERED_TYPE,
                    data=TestObserveEvents.APFEL_FRED_DATA
                )])

                did_push_intermediate_event = True

            total_events_count = 5
            if len(observed_items) == total_events_count:
                break

        assert observed_items[0].event.source == TEST_SOURCE
        assert observed_items[0].event.subject == TestObserveEvents.REGISTERED_SUBJECT
        assert observed_items[0].event.type == TestObserveEvents.REGISTERED_TYPE
        assert observed_items[0].event.data == TestObserveEvents.JANE_DATA
        assert observed_items[1].event.source == TEST_SOURCE
        assert observed_items[1].event.subject == TestObserveEvents.LOGGED_IN_SUBJECT
        assert observed_items[1].event.type == TestObserveEvents.LOGGED_IN_TYPE
        assert observed_items[1].event.data == TestObserveEvents.JANE_DATA
        assert observed_items[2].event.source == TEST_SOURCE
        assert observed_items[2].event.subject == TestObserveEvents.REGISTERED_SUBJECT
        assert observed_items[2].event.type == TestObserveEvents.REGISTERED_TYPE
        assert observed_items[2].event.data == TestObserveEvents.JOHN_DATA
        assert observed_items[3].event.source == TEST_SOURCE
        assert observed_items[3].event.subject == TestObserveEvents.LOGGED_IN_SUBJECT
        assert observed_items[3].event.type == TestObserveEvents.LOGGED_IN_TYPE
        assert observed_items[3].event.data == TestObserveEvents.JOHN_DATA
        assert observed_items[4].event.source == TEST_SOURCE
        assert observed_items[4].event.subject == TestObserveEvents.REGISTERED_SUBJECT
        assert observed_items[4].event.type == TestObserveEvents.REGISTERED_TYPE
        assert observed_items[4].event.data == TestObserveEvents.APFEL_FRED_DATA

    @staticmethod
    @pytest.mark.asyncio
    async def test_observes_event_starting_from_given_event_name(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client
        observed_items = []
        did_push_intermediate_event = False

        async for event in client.observe_events(
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
                await client.write_events([TestObserveEvents.source.new_event(
                    subject=TestObserveEvents.REGISTERED_SUBJECT,
                    event_type=TestObserveEvents.REGISTERED_TYPE,
                    data=TestObserveEvents.APFEL_FRED_DATA
                )])

                did_push_intermediate_event = True

            event_count_after_last_login = 2
            if len(observed_items) == event_count_after_last_login:
                break

        assert observed_items[0].event.source == TEST_SOURCE
        assert observed_items[0].event.subject == TestObserveEvents.LOGGED_IN_SUBJECT
        assert observed_items[0].event.type == TestObserveEvents.LOGGED_IN_TYPE
        assert observed_items[0].event.data == TestObserveEvents.JOHN_DATA
        assert observed_items[1].event.source == TEST_SOURCE
        assert observed_items[1].event.subject == TestObserveEvents.REGISTERED_SUBJECT
        assert observed_items[1].event.type == TestObserveEvents.REGISTERED_TYPE
        assert observed_items[1].event.data == TestObserveEvents.APFEL_FRED_DATA

    @staticmethod
    @pytest.mark.asyncio
    async def test_observes_event_starting_from_given_lower_bound_id(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client
        observed_items = []
        did_push_intermediate_event = False

        async for event in client.observe_events(
            '/users',
            ObserveEventsOptions(
                recursive=True,
                lower_bound_id='2'
            )
        ):
            observed_items.append(event)

            if not did_push_intermediate_event:
                await client.write_events([TestObserveEvents.source.new_event(
                    subject=TestObserveEvents.REGISTERED_SUBJECT,
                    event_type=TestObserveEvents.REGISTERED_TYPE,
                    data=TestObserveEvents.APFEL_FRED_DATA
                )])

                did_push_intermediate_event = True

            event_count_after_given_id = 3
            if len(observed_items) == event_count_after_given_id:
                break

        assert observed_items[0].event.source == TEST_SOURCE
        assert observed_items[0].event.subject == TestObserveEvents.REGISTERED_SUBJECT
        assert observed_items[0].event.type == TestObserveEvents.REGISTERED_TYPE
        assert observed_items[0].event.data == TestObserveEvents.JOHN_DATA
        assert observed_items[1].event.source == TEST_SOURCE
        assert observed_items[1].event.subject == TestObserveEvents.LOGGED_IN_SUBJECT
        assert observed_items[1].event.type == TestObserveEvents.LOGGED_IN_TYPE
        assert observed_items[1].event.data == TestObserveEvents.JOHN_DATA
        assert observed_items[2].event.source == TEST_SOURCE
        assert observed_items[2].event.subject == TestObserveEvents.REGISTERED_SUBJECT
        assert observed_items[2].event.type == TestObserveEvents.REGISTERED_TYPE
        assert observed_items[2].event.data == TestObserveEvents.APFEL_FRED_DATA

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_for_mutually_exclusive_options(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            async for _ in client.observe_events(
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
    @pytest.mark.asyncio
    async def test_throws_error_for_non_integer_lower_bound(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            async for _ in client.observe_events(
                '/users',
                ObserveEventsOptions(
                    recursive=True,
                    lower_bound_id='hello',
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_for_negative_lower_bound(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            async for _ in client.observe_events(
                '/users',
                ObserveEventsOptions(
                    recursive=True,
                    lower_bound_id='-1',
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_for_invalid_subject_in_from_latest_event(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            async for _ in client.observe_events(
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
    @pytest.mark.asyncio
    async def test_throws_error_for_invalid_type_in_from_latest_event(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            async for _ in client.observe_events(
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

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_5xx_status_code(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_observe_events(response: Response) -> Response:
                response.status_code = HTTPStatus.BAD_GATEWAY
                response.set_data(HTTPStatus.BAD_GATEWAY.phrase)
                return response

            attach_handler('/api/observe-events', 'POST', handle_observe_events)

        client= await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.observe_events(
                subject='/',
                options=ObserveEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_protocol_version_does_not_match(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_observe_events(response: Response) -> Response:
                response.headers['X-EventSourcingDB-Protocol-Version'] = '0.0.0'
                response.status_code = HTTPStatus.UNPROCESSABLE_ENTITY
                response.set_data(HTTPStatus.UNPROCESSABLE_ENTITY.phrase)
                return response

            attach_handler('/api/observe-events', 'POST', handle_observe_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ClientError):
            async for _ in client.observe_events(
                '/',
                ObserveEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_4xx_status_code(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_observe_events(response: Response) -> Response:
                response.status_code = HTTPStatus.NOT_FOUND
                response.set_data(HTTPStatus.NOT_FOUND.phrase)
                return response

            attach_handler('/api/observe-events', 'POST', handle_observe_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ClientError):
            async for _ in client.observe_events(
                '/',
                ObserveEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_unexpected_status_code(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_observe_events(response: Response) -> Response:
                response.status_code = HTTPStatus.ACCEPTED
                response.set_data(HTTPStatus.ACCEPTED.phrase)
                return response

            attach_handler('/api/observe-events', 'POST', handle_observe_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.observe_events(
                '/',
                ObserveEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_an_item_that_cannot_be_parsed(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_observe_events(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('cannot be parsed')
                return response

            attach_handler('/api/observe-events', 'POST', handle_observe_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.observe_events(
                '/',
                ObserveEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_an_item_that_has_an_unexpected_type(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_observe_events(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('{"type": "clown", "payload": {"foo": "bar"}}')
                return response

            attach_handler('/api/observe-events', 'POST', handle_observe_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.observe_events(
                '/',
                ObserveEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_an_error_item(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_observe_events(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('{"type": "error", "payload": {"error": "it is just broken"}}')
                return response

            attach_handler('/api/observe-events', 'POST', handle_observe_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.observe_events(
                '/',
                ObserveEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_an_error_item_with_unexpected_payload(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_observe_events(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('{"type": "error", "payload": {"not very correct": "indeed"}}')
                return response

            attach_handler('/api/observe-events', 'POST', handle_observe_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.observe_events(
                '/',
                ObserveEventsOptions(
                    recursive=True
                )
            ):
                pass
