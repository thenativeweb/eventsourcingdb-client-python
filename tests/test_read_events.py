from collections.abc import Callable, Awaitable
from http import HTTPStatus

import pytest

from eventsourcingdb.client import Client
from eventsourcingdb.errors.client_error import ClientError
from eventsourcingdb.errors.invalid_parameter_error import InvalidParameterError
from eventsourcingdb.errors.server_error import ServerError
from eventsourcingdb.handlers.lower_bound import LowerBound
from eventsourcingdb.handlers.read_events import \
    ReadEventsOptions, \
    ReadFromLatestEvent, \
    IfEventIsMissingDuringRead
from eventsourcingdb.handlers.read_events.order import Order
from eventsourcingdb.handlers.upper_bound import UpperBound
from .conftest import TestData

from .shared.database import Database
from .shared.event.assert_event import assert_event_equals
from .shared.start_local_http_server import \
    AttachHandler, \
    Response, \
    AttachHandlers


class TestReadEvents:
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
        prepared_database: Database,
        test_data: TestData
    ):
        client = prepared_database.with_authorization.client

        result = []
        async for event in client.read_events(
            test_data.REGISTERED_SUBJECT,
            ReadEventsOptions(recursive=False)
        ):
            result.append(event)

        registered_count = 2
        assert len(result) == registered_count
        assert_event_equals(
            result[0].event,
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JANE_DATA,
            test_data.TRACE_PARENT_1,
            None
        )
        assert_event_equals(
            result[1].event,
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_3,
            None
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_read_events_from_a_subject_including_children(
        prepared_database: Database,
        test_data: TestData
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
        assert_event_equals(
            result[0].event,
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JANE_DATA,
            test_data.TRACE_PARENT_1,
            None
        )
        assert_event_equals(
            result[1].event,
            test_data.TEST_SOURCE_STRING,
            test_data.LOGGED_IN_SUBJECT,
            test_data.LOGGED_IN_TYPE,
            test_data.JANE_DATA,
            test_data.TRACE_PARENT_2,
            None
        )
        assert_event_equals(
            result[2].event,
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_3,
            None
        )
        assert_event_equals(
            result[3].event,
            test_data.TEST_SOURCE_STRING,
            test_data.LOGGED_IN_SUBJECT,
            test_data.LOGGED_IN_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_4,
            None
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_read_events_in_antichronological_order(
        prepared_database: Database,
        test_data: TestData
    ):
        client = prepared_database.with_authorization.client

        result = []
        async for event in client.read_events(
            test_data.REGISTERED_SUBJECT,
            ReadEventsOptions(recursive=False, order=Order.ANTICHRONOLOGICAL)
        ):
            result.append(event)

        registered_count = 2
        assert len(result) == registered_count
        assert_event_equals(
            result[0].event,
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_3,
            None
        )
        assert_event_equals(
            result[1].event,
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JANE_DATA,
            test_data.TRACE_PARENT_1,
            None
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_read_events_recursive_from_latest_event_in_child_subject(
        prepared_database: Database,
        test_data: TestData
    ):
        client = prepared_database.with_authorization.client

        result = []
        async for event in client.read_events(
            '/users',
            ReadEventsOptions(
                recursive=True,
                from_latest_event=ReadFromLatestEvent(
                    subject=test_data.REGISTERED_SUBJECT,
                    type=test_data.REGISTERED_TYPE,
                    if_event_is_missing=IfEventIsMissingDuringRead.READ_EVERYTHING
                )
            )
        ):
            result.append(event)

        john_count = 2
        assert len(result) == john_count
        assert_event_equals(
            result[0].event,
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_3,
            None
        )
        assert_event_equals(
            result[1].event,
            test_data.TEST_SOURCE_STRING,
            test_data.LOGGED_IN_SUBJECT,
            test_data.LOGGED_IN_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_4,
            None
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_read_events_starting_from_lower_bound(
        prepared_database: Database,
        test_data: TestData
    ):
        client = prepared_database.with_authorization.client

        result = []
        async for event in client.read_events(
            '/users',
            ReadEventsOptions(
                recursive=True,
                lower_bound=LowerBound(id=2, type='inclusive')
            )
        ):
            result.append(event)

        john_count = 2
        assert len(result) == john_count
        assert_event_equals(
            result[0].event,
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_3,
            None
        )
        assert_event_equals(
            result[1].event,
            test_data.TEST_SOURCE_STRING,
            test_data.LOGGED_IN_SUBJECT,
            test_data.LOGGED_IN_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_4,
            None
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_read_events_up_to_the_upper_bound(
        prepared_database: Database,
        test_data: TestData
    ):
        client = prepared_database.with_authorization.client

        result = []
        async for event in client.read_events(
            '/users',
            ReadEventsOptions(
                recursive=True,
                upper_bound=UpperBound(id=2, type='exclusive')
            )
        ):
            result.append(event)

        jane_count = 2
        assert len(result) == jane_count
        assert_event_equals(
            result[0].event,
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JANE_DATA,
            test_data.TRACE_PARENT_1,
            None
        )
        assert_event_equals(
            result[1].event,
            test_data.TEST_SOURCE_STRING,
            test_data.LOGGED_IN_SUBJECT,
            test_data.LOGGED_IN_TYPE,
            test_data.JANE_DATA,
            test_data.TRACE_PARENT_2,
            None
        )

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
                    lower_bound=LowerBound(id='0', type='exclusive'),
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
    async def test_throws_error_for_invalid_lower_bound(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        with pytest.raises(ValueError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    lower_bound=LowerBound(id='hello', type='inclusive')
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
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    lower_bound=LowerBound(id='-1', type='inclusive')
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_for_invalid_upper_bound(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        with pytest.raises(ValueError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    upper_bound=UpperBound(id='hello', type='exclusive')
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_for_negative_upper_bound(
        prepared_database: Database
    ):
        client = prepared_database.with_authorization.client

        with pytest.raises(InvalidParameterError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    upper_bound=UpperBound(id='-1', type='exclusive')
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

            attach_handler('/api/v1/read-events', 'POST', handle_read_events)

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

            attach_handler('/api/v1/read-events', 'POST', handle_read_events)

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

            attach_handler('/api/v1/read-events', 'POST', handle_read_events)

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

            attach_handler('/api/v1/read-events', 'POST', handle_read_events)

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

            attach_handler('/api/v1/read-events', 'POST', handle_read_events)

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

            attach_handler('/api/v1/read-events', 'POST', handle_read_events)

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

            attach_handler('/api/v1/read-events', 'POST', handle_read_events)

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

            attach_handler('/api/v1/read-events', 'POST', handle_read_events)

        client = await get_client(attach_handlers)

        with pytest.raises(ServerError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True
                )
            ):
                pass
