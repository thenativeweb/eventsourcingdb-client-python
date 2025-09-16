import pytest

from eventsourcingdb import EventCandidate
from eventsourcingdb.errors.validation_error import ValidationError
from hashlib import sha256

from ..conftest import TestData
from ..shared.database import Database


class TestVerifyHash:
    @staticmethod
    @pytest.mark.asyncio
    async def test_verifies_the_event_hash(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        written_events = await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING, subject="/test", type="io.eventsourcingdb.test", data={"value": 23}
                )
            ],
        )

        assert len(written_events) == 1

        written_event = written_events[0]
        written_event.verify_hash()

    @staticmethod
    @pytest.mark.asyncio
    async def test_fails_if_the_event_hash_is_invalid(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        written_events = await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING, subject="/test", type="io.eventsourcingdb.test", data={"value": 23}
                )
            ],
        )

        assert len(written_events) == 1

        written_event = written_events[0]

        invalid_hash_data = "invalid data".encode("utf-8")
        invalid_hash = sha256(invalid_hash_data).hexdigest()
        written_event.hash = invalid_hash

        with pytest.raises(ValidationError):
            written_event.verify_hash()
