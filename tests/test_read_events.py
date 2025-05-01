import asyncio

from aiohttp import ClientConnectorDNSError
import pytest

from eventsourcingdb.errors.server_error import ServerError
from eventsourcingdb.handlers.bound import Bound, BoundType
from eventsourcingdb.handlers.read_events import \
    ReadEventsOptions, \
    ReadFromLatestEvent, \
    IfEventIsMissingDuringRead
from eventsourcingdb.handlers.read_events.order import Order

from .conftest import TestData

from .shared.database import Database
from .shared.event.assert_event import assert_event_equals


class TestReadEvents:
    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_is_not_reachable(
        database: Database
    ):
        client = database.get_client("with_invalid_url")

        with pytest.raises(ClientConnectorDNSError):
            async for _ in client.read_events('/', ReadEventsOptions(recursive=False)):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_supports_authorization(
        database: Database
    ):
        client = database.get_client()

        async for _ in client.read_events('/', ReadEventsOptions(recursive=False)):
            pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_read_events_from_a_single_subject(
        prepared_database: Database,
        test_data: TestData
    ):
        client = prepared_database.get_client()

        result = []
        async for event in client.read_events(
            test_data.REGISTERED_SUBJECT,
            ReadEventsOptions(recursive=False)
        ):
            result.append(event)

        registered_count = 2
        assert len(result) == registered_count
        assert_event_equals(
            result[0],
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JANE_DATA,
            test_data.TRACE_PARENT_1,
            None
        )
        assert_event_equals(
            result[1],
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
        client = prepared_database.get_client()

        result = []
        async for event in client.read_events(
            '/users',
            ReadEventsOptions(recursive=True)
        ):
            result.append(event)

        total_event_count = 4
        assert len(result) == total_event_count
        assert_event_equals(
            result[0],
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JANE_DATA,
            test_data.TRACE_PARENT_1,
            None
        )
        assert_event_equals(
            result[1],
            test_data.TEST_SOURCE_STRING,
            test_data.LOGGED_IN_SUBJECT,
            test_data.LOGGED_IN_TYPE,
            test_data.JANE_DATA,
            test_data.TRACE_PARENT_2,
            None
        )
        assert_event_equals(
            result[2],
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_3,
            None
        )
        assert_event_equals(
            result[3],
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
        client = prepared_database.get_client()

        result = []
        async for event in client.read_events(
            test_data.REGISTERED_SUBJECT,
            ReadEventsOptions(recursive=False, order=Order.ANTICHRONOLOGICAL)
        ):
            result.append(event)

        registered_count = 2
        assert len(result) == registered_count
        assert_event_equals(
            result[0],
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_3,
            None
        )
        assert_event_equals(
            result[1],
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
        client = prepared_database.get_client()

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
            result[0],
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_3,
            None
        )
        assert_event_equals(
            result[1],
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
        client = prepared_database.get_client()

        result = []
        async for event in client.read_events(
            '/users',
            ReadEventsOptions(
                recursive=True,
                lower_bound=Bound(id='2', type=BoundType.INCLUSIVE)
            )
        ):
            result.append(event)

        john_count = 2
        assert len(result) == john_count
        assert_event_equals(
            result[0],
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_3,
            None
        )
        assert_event_equals(
            result[1],
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
        client = prepared_database.get_client()

        result = []
        async for event in client.read_events(
            '/users',
            ReadEventsOptions(
                recursive=True,
                upper_bound=Bound(id='2', type=BoundType.EXCLUSIVE)
            )
        ):
            result.append(event)

        jane_count = 2
        assert len(result) == jane_count
        assert_event_equals(
            result[0],
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JANE_DATA,
            test_data.TRACE_PARENT_1,
            None
        )
        assert_event_equals(
            result[1],
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
        client = prepared_database.get_client()

        with pytest.raises(ServerError):
            async for _ in client.read_events(
                '/users',
                ReadEventsOptions(
                    recursive=True,
                    from_latest_event=ReadFromLatestEvent(
                        subject='/',
                        type='com.foo.bar',
                        if_event_is_missing=IfEventIsMissingDuringRead.READ_EVERYTHING
                    ),
                    lower_bound=Bound(id='0', type=BoundType.INCLUSIVE),
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_for_invalid_subject(
        prepared_database: Database
    ):
        client = prepared_database.get_client()

        with pytest.raises(ServerError):
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
        client = prepared_database.get_client()

        with pytest.raises(ServerError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    lower_bound=Bound(id='hello', type=BoundType.INCLUSIVE)
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_for_negative_lower_bound(
        prepared_database: Database
    ):
        client = prepared_database.get_client()

        with pytest.raises(ServerError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    lower_bound=Bound(id='-1', type=BoundType.INCLUSIVE)
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_for_invalid_upper_bound(
        prepared_database: Database
    ):
        client = prepared_database.get_client()

        with pytest.raises(ServerError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    upper_bound=Bound(id='hello', type=BoundType.INCLUSIVE)
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_for_negative_upper_bound(
        prepared_database: Database
    ):
        client = prepared_database.get_client()

        with pytest.raises(ServerError):
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(
                    recursive=True,
                    upper_bound=Bound(id='-1', type=BoundType.EXCLUSIVE)
                )
            ):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_for_invalid_subject_in_from_latest_event(
        prepared_database: Database
    ):
        client = prepared_database.get_client()

        with pytest.raises(ServerError):
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
        client = prepared_database.get_client()

        with pytest.raises(ServerError):
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

    @staticmethod
    @pytest.mark.asyncio
    async def test_cancelling_read_events_async(
        prepared_database: Database,
    ):
        client = prepared_database.get_client()
        events_processed = 0
        events_to_process = 2

        async def process_events():
            nonlocal events_processed
            async for _ in client.read_events(
                '/',
                ReadEventsOptions(recursive=True)
            ):
                events_processed += 1
                await asyncio.sleep(0.25)

        task = asyncio.create_task(process_events())
        await asyncio.sleep(0.7)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        assert task.done(), 'Task should be completed after cancellation'
        assert task.cancelled(), 'Task should be marked as cancelled'

        try:
            task.exception()
        except asyncio.CancelledError:
            pass

        assert events_processed > events_to_process, (
            'Expected to process some events before cancellation'
        )
