from collections.abc import Callable, Awaitable
from http import HTTPStatus

import pytest
import pytest_asyncio

from eventsourcingdb_client_python.client import Client
from eventsourcingdb_client_python.errors.client_error import ClientError
from eventsourcingdb_client_python.errors.invalid_parameter_error import InvalidParameterError
from eventsourcingdb_client_python.errors.server_error import ServerError
from eventsourcingdb_client_python.event.source import Source
from eventsourcingdb_client_python.handlers.read_events import \
    ReadEventsOptions, \
    ReadFromLatestEvent, \
    IfEventIsMissingDuringRead
from eventsourcingdb_client_python.handlers.read_events.order import Order

from .shared.build_database import build_database
from .shared.database import Database
from .shared.event.assert_event import assert_event
from .shared.event.test_source import TEST_SOURCE
from .shared.start_local_http_server import \
    StopServer, \
    AttachHandler, \
    start_local_http_server, \
    Response, AttachHandlers


@pytest_asyncio.fixture
async def prepared_database(
    database: Database
) -> Database:
    await database.with_authorization.client.write_events([
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

    return database


class TestReadEvents:
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
    @pytest.mark.asyncio
    async def test_throws_error_if_server_is_not_reachable(
        database: Database
    ):
        client = database.with_invalid_url.client

        with pytest.raises(ServerError):
            async for _ in client.read_events('/', ReadEventsOptions(recursive=False)):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_supports_authorization(
        database: Database
    ):
        client = database.with_authorization.client

        async for _ in client.read_events('/', ReadEventsOptions(recursive=False)):
            pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_read_events_from_a_single_subject(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        result = []
        async for event in client.read_events(
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
    @pytest.mark.asyncio
    async def test_read_events_from_a_subject_including_children(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        result = []
        async for event in client.read_events(
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
    @pytest.mark.asyncio
    async def test_read_events_in_antichronological_order(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        result = []
        async for event in client.read_events(
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
    @pytest.mark.asyncio
    async def test_read_events_matching_event_names(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        result = []
        async for event in client.read_events(
            '/users',
            ReadEventsOptions(
                recursive=True,
                from_latest_event=ReadFromLatestEvent(
                    subject=TestReadEvents.REGISTERED_SUBJECT,
                    type=TestReadEvents.REGISTERED_TYPE,
                    if_event_is_missing=IfEventIsMissingDuringRead.READ_EVERYTHING
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
    @pytest.mark.asyncio
    async def test_read_events_starting_from_lower_bound_id(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        result = []
        async for event in client.read_events(
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
    @pytest.mark.asyncio
    async def test_read_events_up_to_the_upper_bound_id(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        result = []
        async for event in client.read_events(
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
    @pytest.mark.asyncio
    async def test_throws_error_for_exclusive_options(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            async for _ in client.read_events(
                '/users',
                ReadEventsOptions(
                    recursive=True,
                    from_latest_event=ReadFromLatestEvent(
                        subject='/',
                        type='com.foo.bar',
                        if_event_is_missing=IfEventIsMissingDuringRead.READ_EVERYTHING
                    ),
                    lower_bound_id='0'
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_for_invalid_subject(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            async for _ in client.read_events(
                '',
                ReadEventsOptions(
                    recursive=True
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_for_invalid_lower_bound_id(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    lower_bound_id='hello'
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_for_negative_lower_bound_id(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    lower_bound_id='-1'
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_for_invalid_upper_bound_id(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    upper_bound_id='hello'
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_for_negative_upper_bound_id(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    upper_bound_id='-1'
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
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    from_latest_event=ReadFromLatestEvent(
                        subject='',
                        type='com.foo.bar',
                        if_event_is_missing=IfEventIsMissingDuringRead.READ_EVERYTHING
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
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    from_latest_event=ReadFromLatestEvent(
                        subject='/',
                        type='',
                        if_event_is_missing=IfEventIsMissingDuringRead.READ_EVERYTHING
                    )
                )
            ):
                pass


class TestReadEventsWithMockServer:
    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_responds_with_5xx_status_code(
        get_client: Callable[[AttachHandlers], Awaitable[Client]]
    ):
        def attach_handlers(attach_handler: AttachHandler):
            def handle_read_events(response: Response) -> Response:
                response.status_code = HTTPStatus.BAD_GATEWAY
                response.set_data(HTTPStatus.BAD_GATEWAY.phrase)
                return response

            attach_handler('/api/read-events', 'POST', handle_read_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
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
            def handle_read_events(response: Response) -> Response:
                response.headers['X-EventSourcingDB-Protocol-Version'] = '0.0.0'
                response.status_code = HTTPStatus.UNPROCESSABLE_ENTITY
                response.set_data(HTTPStatus.UNPROCESSABLE_ENTITY.phrase)
                return response

            attach_handler('/api/read-events', 'POST', handle_read_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ClientError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
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
            def handle_read_events(response: Response) -> Response:
                response.status_code = HTTPStatus.NOT_FOUND
                response.set_data(HTTPStatus.NOT_FOUND.phrase)
                return response

            attach_handler('/api/read-events', 'POST', handle_read_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ClientError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
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
            def handle_read_events(response: Response) -> Response:
                response.status_code = HTTPStatus.ACCEPTED
                response.set_data(HTTPStatus.ACCEPTED.phrase)
                return response

            attach_handler('/api/read-events', 'POST', handle_read_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
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
            def handle_read_events(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('cannot be parsed')
                return response

            attach_handler('/api/read-events', 'POST', handle_read_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
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
            def handle_read_events(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('{"type": "clown", "payload": {"foo": "bar"}}')
                return response

            attach_handler('/api/read-events', 'POST', handle_read_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
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
            def handle_read_events(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('{"type": "error", "payload": {"error": "it is just broken"}}')
                return response

            attach_handler('/api/read-events', 'POST', handle_read_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
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
            def handle_read_events(response: Response) -> Response:
                response.status_code = HTTPStatus.OK
                response.set_data('{"type": "error", "payload": {"not very correct": "indeed"}}')
                return response

            attach_handler('/api/read-events', 'POST', handle_read_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True
                )
            ):
                pass
