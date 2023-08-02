import pytest

from eventsourcingdb_client_python.errors.client_error import ClientError
from .conftest import TestData
from .shared.build_database import build_database
from .shared.database import Database


class TestRegisterEventSchema:
    @classmethod
    def setup_class(cls):
        build_database('tests/shared/docker/eventsourcingdb')

    @staticmethod
    @pytest.mark.asyncio
    async def test_registers_new_schema_if_it_doesnt_conflict_with_existing_events(
        database: Database,
    ):
        client = database.with_authorization.client

        await client.register_event_schema("com.bar.baz", '{"type":"object"}')

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_schema_conflicts_with_existing_events(
        database: Database,
        test_data: TestData,
    ):
        client = database.with_authorization.client

        await client.write_events([
            test_data.TEST_SOURCE.new_event(
                subject="/",
                event_type="com.gornisht.ekht",
                data={
                    "oy": "gevalt",
                },
            )
        ])

        with pytest.raises(ClientError, match="additionalProperties"):
            await client.register_event_schema(
                "com.gornisht.ekht",
                '{"type":"object","additionalProperties":false}'
            )

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_schema_already_exists(
        database: Database,
    ):
        client = database.with_authorization.client

        await client.register_event_schema(
            "com.gornisht.ekht",
            '{"type":"object","additionalProperties":false}'
        )

        with pytest.raises(ClientError, match="schema already exists"):
            await client.register_event_schema(
                "com.gornisht.ekht",
                '{"type":"object","additionalProperties":false}'
            )

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_schema_is_invalid(
        database: Database,
    ):
        client = database.with_authorization.client

        with pytest.raises(ClientError, match="'/type' does not validate"):
            await client.register_event_schema("com.gornisht.ekht", '{"type":"gurkenwasser"}')
