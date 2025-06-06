import pytest
from eventsourcingdb import ServerError
from eventsourcingdb import EventCandidate

from .conftest import TestData

from .shared.database import Database


class TestRegisterEventSchema:
    @staticmethod
    @pytest.mark.asyncio
    async def test_registers_new_schema_if_it_doesnt_conflict_with_existing_events(
        database: Database,
    ) -> None:
        client = database.get_client()

        await client.register_event_schema(
            "com.bar.baz",
            {
                "type": "object",
                "properties": {}
            }
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_schema_conflicts_with_existing_events(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING,
                    subject="/",
                    type="com.gornisht.ekht",
                    data={
                        "oy": "gevalt",
                    },
                )
            ]
        )

        with pytest.raises(ServerError, match='missing properties'):
            await client.register_event_schema(
                "com.gornisht.ekht",
                {
                    "type": "object",
                    "additionalProperties": False
                }
            )

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_schema_already_exists(
        database: Database,
    ) -> None:
        client = database.get_client()

        await client.register_event_schema(
            "com.gornisht.ekht",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False
            }
        )

        with pytest.raises(ServerError, match='schema already exists'):
            await client.register_event_schema(
                "com.gornisht.ekht",
                {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False
                }
            )

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_schema_is_invalid(
        database: Database,
    ) -> None:
        client = database.get_client()

        with pytest.raises(ServerError, match='value must be "object"'):
            await client.register_event_schema(
                "com.gornisht.ekht",
                {
                    "type": "gurkenwasser",
                    "properties": {}
                }
            )
