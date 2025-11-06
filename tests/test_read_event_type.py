import pytest

from eventsourcingdb import EventCandidate, EventType
from eventsourcingdb.errors.server_error import ServerError

from .conftest import TestData
from .shared.database import Database


class TestReadEventType:
    @staticmethod
    @pytest.mark.asyncio
    async def test_fails_if_the_event_type_does_not_exist(
        database: Database,
    ) -> None:
        with pytest.raises(ServerError, match="event type .* not found"):
            await database.get_client().read_event_type("non.existent.event.type")

    @staticmethod
    @pytest.mark.asyncio
    async def test_fails_if_the_event_type_is_malformed(
        database: Database,
    ) -> None:
        with pytest.raises(ServerError, match="invalid event type"):
            await database.get_client().read_event_type("malformed.event.type.")

    @staticmethod
    @pytest.mark.asyncio
    async def test_read_an_existing_event_type(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client("with_authorization")
        await client.write_events(
            [
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
            ]
        )

        event_type = await client.read_event_type("com.foo.bar")

        assert isinstance(event_type, EventType)
        assert event_type.event_type == "com.foo.bar"
        assert event_type.is_phantom is False
        assert event_type.schema is None
