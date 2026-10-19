import json
from hashlib import sha256

import pytest

from eventsourcingdb import (
    Event,
    EventCandidate,
    HashVerificationFailedError,
    ReadEventsOptions,
    UnsupportedHashVersionError,
    ValidationError,
)

from ..conftest import TestData
from ..shared.database import Database
from ..shared.serve_events import read_events_from, write_events_to
from ..shared.stream_server import Api
from .fixtures import (
    READ_EVENTS_FROM_V2_API,
    READ_EVENTS_WITH_HASH_V1,
    READ_EVENTS_WITH_HASH_V2,
    WRITTEN_EVENTS_FROM_V2_API,
    WRITTEN_EVENTS_WITH_HASH_V1,
    WRITTEN_EVENTS_WITH_HASH_V2,
)

# The events with hashes of either version as the v1 API sends them, and
# with hashes of version 2 as the v2 API sends them.
READ_EVENTS = [
    pytest.param(READ_EVENTS_WITH_HASH_V1, 'v1', id='v1'),
    pytest.param(READ_EVENTS_WITH_HASH_V2, 'v1', id='v2'),
    pytest.param(READ_EVENTS_FROM_V2_API, 'v2', id='v2 from the v2 API'),
]
WRITTEN_EVENTS = [
    pytest.param(WRITTEN_EVENTS_WITH_HASH_V1, 'v1', id='v1'),
    pytest.param(WRITTEN_EVENTS_WITH_HASH_V2, 'v1', id='v2'),
    pytest.param(WRITTEN_EVENTS_FROM_V2_API, 'v2', id='v2 from the v2 API'),
]
EVENTS_WITH_HASH_V2 = [
    pytest.param(READ_EVENTS_WITH_HASH_V2, 'v1', id='v1 API'),
    pytest.param(READ_EVENTS_FROM_V2_API, 'v2', id='v2 API'),
]


def count_written_events(response_text: str, api: Api) -> int:
    if api == 'v1':
        return len(json.loads(response_text))

    return sum(json.loads(line)['type'] == 'event' for line in response_text.splitlines())


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
    async def test_verifies_the_hash_of_events_whose_data_python_writes_differently(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        written_events = await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING,
                    subject="/books/42",
                    type="io.eventsourcingdb.library.book-acquired",
                    data={"title": "2001 – A Space Odyssey", "notes": "<b>&</b>"},
                    trace_parent=test_data.TRACE_PARENT_1,
                )
            ],
        )

        assert len(written_events) == 1
        written_events[0].verify_hash()

        read_events = [
            event
            async for event in client.read_events("/books/42", ReadEventsOptions(recursive=False))
        ]

        assert len(read_events) == 1
        read_events[0].verify_hash()

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

        invalid_hash_data = b"invalid data"
        invalid_hash = sha256(invalid_hash_data).hexdigest()
        written_event.hash = invalid_hash

        with pytest.raises(HashVerificationFailedError) as error:
            written_event.verify_hash()

        assert isinstance(error.value, ValidationError)


class TestVerifyHashOfFixedEvents:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('lines', 'api'), READ_EVENTS)
    async def test_verifies_the_hash_of_read_events(lines: list[str], api: Api) -> None:
        events = await read_events_from(lines, api)

        assert len(events) == len(lines)
        for event in events:
            event.verify_hash()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('response_text', 'api'), WRITTEN_EVENTS)
    async def test_verifies_the_hash_of_written_events(response_text: str, api: Api) -> None:
        events = await write_events_to(response_text, api)

        assert len(events) == count_written_events(response_text, api)
        for event in events:
            event.verify_hash()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('lines', 'api'), READ_EVENTS)
    async def test_fails_if_a_field_was_changed(lines: list[str], api: Api) -> None:
        events = await read_events_from(
            [line.replace('/books/42', '/books/23') for line in lines], api
        )

        for event in events:
            with pytest.raises(HashVerificationFailedError, match='Failed to verify hash.'):
                event.verify_hash()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('lines', 'api'), READ_EVENTS)
    async def test_fails_if_the_data_was_changed_after_it_was_received(lines: list[str], api: Api) -> None:
        events = await read_events_from(lines, api)

        for event in events:
            event.data['title'] = 'Dune'

            with pytest.raises(HashVerificationFailedError, match='Failed to verify hash.'):
                event.verify_hash()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('lines', 'api'), READ_EVENTS)
    async def test_fails_if_the_hash_was_changed(lines: list[str], api: Api) -> None:
        events = await read_events_from(lines, api)

        for event in events:
            event.hash = event.hash[:-1] + ('0' if event.hash[-1] != '0' else '1')

            with pytest.raises(HashVerificationFailedError, match='Failed to verify hash.'):
                event.verify_hash()

    @staticmethod
    @pytest.mark.parametrize(('lines', 'api'), READ_EVENTS)
    def test_verifies_the_hash_of_an_event_parsed_from_a_dict(lines: list[str], api: Api) -> None:
        # Without the data as the server sent it, the hash is computed over the
        # data serialized again, which only matches for data that Python writes
        # like the server does, such as that of the second event.
        event = Event.parse(json.loads(lines[1])['payload' if api == 'v1' else 'data'])

        event.verify_hash()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('lines', 'api'), EVENTS_WITH_HASH_V2)
    async def test_fails_if_a_trace_field_of_an_event_with_a_hash_of_version_2_was_changed(
        lines: list[str], api: Api
    ) -> None:
        # Unlike version 1, version 2 also covers traceparent and tracestate.
        events = await read_events_from([line.replace('foo=bar', 'foo=baz') for line in lines], api)

        events[0].verify_hash()
        with pytest.raises(HashVerificationFailedError, match='Failed to verify hash.'):
            events[1].verify_hash()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('lines', 'api'), EVENTS_WITH_HASH_V2)
    async def test_fails_with_the_version_if_the_hash_is_of_an_unknown_version(
        lines: list[str], api: Api
    ) -> None:
        events = await read_events_from(
            [line.replace('esdb:hash:v2:', 'esdb:hash:v3:') for line in lines], api
        )

        for event in events:
            with pytest.raises(UnsupportedHashVersionError, match="Hash version 'v3' is not supported.") as error:
                event.verify_hash()

            assert error.value.version == 'v3'
            assert isinstance(error.value, ValidationError)
