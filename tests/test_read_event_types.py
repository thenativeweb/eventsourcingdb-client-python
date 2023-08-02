import pytest

from eventsourcingdb_client_python.handlers.read_event_types.event_type import EventType
from .conftest import TestData
from .shared.build_database import build_database
from .shared.database import Database


class TestReadEventTypes:
    @classmethod
    def setup_class(cls):
        build_database('tests/shared/docker/eventsourcingdb')

    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_all_types_of_existing_events_and_registered_schemas(
        database: Database,
        test_data: TestData,
    ):
        client = database.with_authorization.client

        await client.write_events([
            test_data.TEST_SOURCE.new_event(
                subject="/account",
                event_type="com.foo.bar",
                data={},
            ),
            test_data.TEST_SOURCE.new_event(
                subject="/account/user",
                event_type="com.bar.baz",
                data={},
            ),
            test_data.TEST_SOURCE.new_event(
                subject="/account/user",
                event_type="com.baz.leml",
                data={},
            ),
            test_data.TEST_SOURCE.new_event(
                subject="/",
                event_type="com.quux.knax",
                data={},
            ),
        ])

        await client.register_event_schema("org.ban.ban", '{"type":"object"}')
        await client.register_event_schema("org.bing.chilling", '{"type":"object"}')

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
                schema='{"type":"object"}',
            ),
            EventType(
                event_type="org.bing.chilling",
                is_phantom=True,
                schema='{"type":"object"}',
            ),
        }

        assert actual_event_types == expected_event_types
