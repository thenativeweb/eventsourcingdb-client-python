import asyncio
from aiohttp import ClientConnectorDNSError
import pytest

from eventsourcingdb.errors.server_error import ServerError
from eventsourcingdb.event.event_candidate import EventCandidate
from eventsourcingdb.handlers.bound import Bound, BoundType
# pylint: disable=C0301
from eventsourcingdb.handlers.observe_events.if_event_is_missing_during_observe import IfEventIsMissingDuringObserve
from eventsourcingdb.handlers.observe_events.observe_events_options import ObserveEventsOptions
from eventsourcingdb.handlers.observe_events.observe_from_latest_event import ObserveFromLatestEvent

from .conftest import TestData

from .shared.database import Database
from .shared.event.assert_event import assert_event_equals


class TestObserveEvents:
    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_is_not_reachable(
        database: Database
    ):
        client = database.get_client("with_invalid_url")

        with pytest.raises(ClientConnectorDNSError):
            async for _ in client.observe_events('/', ObserveEventsOptions(recursive=False)):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_subject_is_invalid(
        database: Database
    ):
        client = database.get_client()

        with pytest.raises(ServerError):
            async for _ in client.observe_events('', ObserveEventsOptions(recursive=False)):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_supports_authorization(
        prepared_database: Database
    ):
        client = prepared_database.get_client()

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
        prepared_database: Database,
        test_data: TestData
    ):
        client = prepared_database.get_client()
        registered_events_count = 3

        observed_items = []

        events = client.observe_events(
            test_data.REGISTERED_SUBJECT,
            ObserveEventsOptions(recursive=False)
        )

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING,
                    subject=test_data.REGISTERED_SUBJECT,
                    type=test_data.REGISTERED_TYPE,
                    data=test_data.APFEL_FRED_DATA,
                    trace_parent=test_data.TRACE_PARENT_5,
                )
            ]
        )

        async for event in events:
            observed_items.append(event)

            if len(observed_items) == registered_events_count:
                break

        assert_event_equals(
            observed_items[0],
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JANE_DATA,
            test_data.TRACE_PARENT_1,
            None
        )
        assert_event_equals(
            observed_items[1],
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_3,
            None
        )
        assert_event_equals(
            observed_items[2],
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.APFEL_FRED_DATA,
            test_data.TRACE_PARENT_5,
            None
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_observes_event_from_a_subject_including_child_subjects(
        prepared_database: Database,
        test_data: TestData
    ):
        client = prepared_database.get_client()
        observed_items = []
        did_push_intermediate_event = False

        async for event in client.observe_events(
            '/users',
            ObserveEventsOptions(recursive=True)
        ):
            observed_items.append(event)

            if not did_push_intermediate_event:
                await client.write_events(
                    [
                        EventCandidate(
                            source=test_data.TEST_SOURCE_STRING,
                            subject=test_data.REGISTERED_SUBJECT,
                            type=test_data.REGISTERED_TYPE,
                            data=test_data.APFEL_FRED_DATA,
                            trace_parent=test_data.TRACE_PARENT_5,
                        )
                    ]
                )

                did_push_intermediate_event = True

            total_events_count = 5
            if len(observed_items) == total_events_count:
                break

        assert_event_equals(
            observed_items[0],
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JANE_DATA,
            test_data.TRACE_PARENT_1,
            None
        )
        assert_event_equals(
            observed_items[1],
            test_data.TEST_SOURCE_STRING,
            test_data.LOGGED_IN_SUBJECT,
            test_data.LOGGED_IN_TYPE,
            test_data.JANE_DATA,
            test_data.TRACE_PARENT_2,
            None
        )
        assert_event_equals(
            observed_items[2],
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_3,
            None
        )
        assert_event_equals(
            observed_items[3],
            test_data.TEST_SOURCE_STRING,
            test_data.LOGGED_IN_SUBJECT,
            test_data.LOGGED_IN_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_4,
            None
        )
        assert_event_equals(
            observed_items[4],
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.APFEL_FRED_DATA,
            test_data.TRACE_PARENT_5,
            None
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_observes_event_starting_from_given_event_name(
        prepared_database: Database,
        test_data: TestData
    ):
        client = prepared_database.get_client()
        observed_items = []
        did_push_intermediate_event = False

        async for event in client.observe_events(
            '/users',
            ObserveEventsOptions(
                recursive=True,
                from_latest_event=ObserveFromLatestEvent(
                    subject=test_data.LOGGED_IN_SUBJECT,
                    type=test_data.LOGGED_IN_TYPE,
                    if_event_is_missing=IfEventIsMissingDuringObserve.READ_EVERYTHING
                )
            )
        ):
            observed_items.append(event)

            if not did_push_intermediate_event:
                await client.write_events(
                    [
                        EventCandidate(
                            source=test_data.TEST_SOURCE_STRING,
                            subject=test_data.REGISTERED_SUBJECT,
                            type=test_data.REGISTERED_TYPE,
                            data=test_data.APFEL_FRED_DATA,
                            trace_parent=test_data.TRACE_PARENT_5,
                        )
                    ]
                )

                did_push_intermediate_event = True

            event_count_after_last_login = 2
            if len(observed_items) == event_count_after_last_login:
                break

        assert_event_equals(
            observed_items[0],
            test_data.TEST_SOURCE_STRING,
            test_data.LOGGED_IN_SUBJECT,
            test_data.LOGGED_IN_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_4,
            None
        )
        assert_event_equals(
            observed_items[1],
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.APFEL_FRED_DATA,
            test_data.TRACE_PARENT_5,
            None
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_observes_event_starting_from_given_lower_bound(
        prepared_database: Database,
        test_data: TestData
    ):
        client = prepared_database.get_client()
        observed_items = []
        did_push_intermediate_event = False

        async for event in client.observe_events(
            '/users',
            ObserveEventsOptions(
                recursive=True,
                lower_bound=Bound(
                    id='2',
                    type=BoundType.INCLUSIVE
                )
            )
        ):
            observed_items.append(event)

            if not did_push_intermediate_event:
                await client.write_events(
                    [
                        EventCandidate(
                            source=test_data.TEST_SOURCE_STRING,
                            subject=test_data.REGISTERED_SUBJECT,
                            type=test_data.REGISTERED_TYPE,
                            data=test_data.APFEL_FRED_DATA,
                            trace_parent=test_data.TRACE_PARENT_5,
                        )
                    ]
                )

                did_push_intermediate_event = True

            event_count_after_given_id = 3
            if len(observed_items) == event_count_after_given_id:
                break

        assert_event_equals(
            observed_items[0],
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_3,
            None
        )
        assert_event_equals(
            observed_items[1],
            test_data.TEST_SOURCE_STRING,
            test_data.LOGGED_IN_SUBJECT,
            test_data.LOGGED_IN_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_4,
            None
        )
        assert_event_equals(
            observed_items[2],
            test_data.TEST_SOURCE_STRING,
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.APFEL_FRED_DATA,
            test_data.TRACE_PARENT_5,
            None
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_for_mutually_exclusive_options(
        prepared_database: Database
    ):
        client = prepared_database.get_client()

        with pytest.raises(ServerError):
            async for _ in client.observe_events(
                '/users',
                ObserveEventsOptions(
                    recursive=True,
                    lower_bound=Bound(
                        id='3',
                        type=BoundType.EXCLUSIVE
                    ),
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
    async def test_throws_error_for_invalid_subject_in_from_latest_event(
        prepared_database: Database
    ):
        client = prepared_database.get_client()

        with pytest.raises(ServerError):
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
        client = prepared_database.get_client()

        with pytest.raises(ServerError):
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

    @staticmethod
    @pytest.mark.asyncio
    async def test_cancelling_observe_events_async(
        prepared_database: Database,
    ):
        client = prepared_database.get_client()
        events_processed = 0
        events_to_process = 2

        async def process_events():
            nonlocal events_processed
            async for _ in client.observe_events(
                '/',
                ObserveEventsOptions(
                    recursive=True,
                    from_latest_event=None
                )
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
