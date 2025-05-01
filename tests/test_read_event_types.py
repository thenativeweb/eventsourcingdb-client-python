import pytest

from eventsourcingdb.event.event_candidate import EventCandidate
from eventsourcingdb.handlers.read_event_types.event_type import EventType

from .conftest import TestData

from .shared.database import Database


class TestReadEventTypes:
    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_all_types_of_existing_events_and_registered_schemas(
        database: Database,
        test_data: TestData,
    ):
        client = database.get_client("with_authorization")

        await client.write_events([
            EventCandidate(
                source=test_data.TEST_SOURCE_STRING,
                subject="/account",
                type="com.foo.bar",
                data={},
            ),
            EventCandidate(
                source=test_data.TEST_SOURCE_STRING,
                subject="/account/user",
                type="com.bar.baz",
                data={},
            ),
            EventCandidate(
                source=test_data.TEST_SOURCE_STRING,
                subject="/account/user",
                type="com.baz.leml",
                data={},
            ),
            EventCandidate(
                source=test_data.TEST_SOURCE_STRING,
                subject="/",
                type="com.quux.knax",
                data={},
            ),
        ])

        await client.register_event_schema(
            "org.ban.ban",
            {"type": "object", "properties": {}}
        )
        await client.register_event_schema(
            "org.bing.chilling",
            {"type": "object", "properties": {}}
        )

        actual_event_types: set[EventType] = set()
        async for event_type in client.read_event_types():
            actual_event_types.add(event_type)

        expected_event_types = {
            EventType(
                event_type="com.foo.bar",
                is_phantom=False,
                schema=None,
            ),
            EventType(
                event_type="com.bar.baz",
                is_phantom=False,
                schema=None,
            ),
            EventType(
                event_type="com.baz.leml",
                is_phantom=False,
                schema=None,
            ),
            EventType(
                event_type="com.quux.knax",
                is_phantom=False,
                schema=None,
            ),
            EventType(
                event_type="org.ban.ban",
                is_phantom=True,
                schema={"type": "object", "properties": {}},  # Updated expected schema
            ),
            EventType(
                event_type="org.bing.chilling",
                is_phantom=True,
                schema={"type": "object", "properties": {}},  # Updated expected schema
            ),
        }

        assert actual_event_types == expected_event_types
