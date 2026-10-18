import pytest

from eventsourcingdb import DbApiError, ErrorCode, EventCandidate

from .conftest import TestData
from .shared.database import Database


class TestRegisterEventSchema:
    @staticmethod
    @pytest.mark.asyncio
    async def test_registers_new_schema_if_it_doesnt_conflict_with_existing_events(
        database: Database,
    ) -> None:
        client = database.get_client()

        await client.register_event_schema("com.bar.baz", {"type": "object", "properties": {}})

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

        with pytest.raises(DbApiError, match="additionalProperties 'oy' not allowed") as error:
            await client.register_event_schema(
                "com.gornisht.ekht",
                {"type": "object", "properties": {}, "additionalProperties": False},
            )

        assert error.value.code == ErrorCode.EVENT_SCHEMA_VIOLATED

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_schema_already_exists(
        database: Database,
    ) -> None:
        client = database.get_client()

        await client.register_event_schema(
            "com.gornisht.ekht", {"type": "object", "properties": {}, "additionalProperties": False}
        )

        with pytest.raises(DbApiError) as error:
            await client.register_event_schema(
                "com.gornisht.ekht",
                {"type": "object", "properties": {}, "additionalProperties": False},
            )

        assert error.value.code == ErrorCode.EVENT_SCHEMA_ALREADY_REGISTERED

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_schema_is_invalid(
        database: Database,
    ) -> None:
        client = database.get_client()

        with pytest.raises(DbApiError, match='value must be') as error:
            await client.register_event_schema(
                "com.gornisht.ekht", {"type": "gurkenwasser", "properties": {}}
            )

        # The v1 API rejects the request with status 400, while the v2 API
        # reports the schema as malformed.
        if await database.offers_v2_api():
            assert error.value.code == ErrorCode.EVENT_SCHEMA_MALFORMED
        else:
            assert (error.value.status, error.value.code) == (400, None)
