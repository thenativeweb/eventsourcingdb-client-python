import json
from hashlib import sha256

import pytest
from aiohttp import web

from eventsourcingdb import (
    Event,
    EventCandidate,
    ReadEventsOptions,
    UnsupportedHashVersionError,
)
from eventsourcingdb.errors.validation_error import ValidationError

from ..conftest import TestData
from ..shared.database import Database
from ..shared.stream_server import StreamServer
from .fixtures import (
    READ_EVENTS_WITH_HASH_V1,
    READ_EVENTS_WITH_HASH_V2,
    WRITTEN_EVENTS_WITH_HASH_V1,
    WRITTEN_EVENTS_WITH_HASH_V2,
)

READ_EVENTS = [
    pytest.param(READ_EVENTS_WITH_HASH_V1, id='v1'),
    pytest.param(READ_EVENTS_WITH_HASH_V2, id='v2'),
]
WRITTEN_EVENTS = [
    pytest.param(WRITTEN_EVENTS_WITH_HASH_V1, id='v1'),
    pytest.param(WRITTEN_EVENTS_WITH_HASH_V2, id='v2'),
]


async def read_events_from(lines: list[str]) -> list[Event]:
    async def write_stream(response: web.StreamResponse) -> None:
        for line in lines:
            await response.write(line.encode('utf-8') + b'\n')

    async with StreamServer(write_stream) as server:
        return [
            event
            async for event in server.get_client().read_events(
                '/books/42', ReadEventsOptions(recursive=False)
            )
        ]


async def write_events_to(response_text: str) -> list[Event]:
    async def write_stream(response: web.StreamResponse) -> None:
        await response.write(response_text.encode('utf-8'))

    async with StreamServer(write_stream) as server:
        return await server.get_client().write_events(
            [
                EventCandidate(
                    source='https://www.eventsourcingdb.io',
                    subject='/books/42',
                    type='io.eventsourcingdb.library.book-acquired',
                    data={},
                )
            ]
        )


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

        with pytest.raises(ValidationError):
            written_event.verify_hash()


class TestVerifyHashOfFixedEvents:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('lines', READ_EVENTS)
    async def test_verifies_the_hash_of_read_events(lines: list[str]) -> None:
        events = await read_events_from(lines)

        assert len(events) == len(lines)
        for event in events:
            event.verify_hash()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('response_text', WRITTEN_EVENTS)
    async def test_verifies_the_hash_of_written_events(response_text: str) -> None:
        events = await write_events_to(response_text)

        assert len(events) == len(json.loads(response_text))
        for event in events:
            event.verify_hash()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('lines', READ_EVENTS)
    async def test_fails_if_a_field_was_changed(lines: list[str]) -> None:
        events = await read_events_from([line.replace('/books/42', '/books/23') for line in lines])

        for event in events:
            with pytest.raises(ValidationError, match='Failed to verify hash.'):
                event.verify_hash()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('lines', READ_EVENTS)
    async def test_fails_if_the_data_was_changed_after_it_was_received(lines: list[str]) -> None:
        events = await read_events_from(lines)

        for event in events:
            event.data['title'] = 'Dune'

            with pytest.raises(ValidationError, match='Failed to verify hash.'):
                event.verify_hash()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('lines', READ_EVENTS)
    async def test_fails_if_the_hash_was_changed(lines: list[str]) -> None:
        events = await read_events_from(lines)

        for event in events:
            event.hash = event.hash[:-1] + ('0' if event.hash[-1] != '0' else '1')

            with pytest.raises(ValidationError, match='Failed to verify hash.'):
                event.verify_hash()

    @staticmethod
    @pytest.mark.parametrize('lines', READ_EVENTS)
    def test_verifies_the_hash_of_an_event_parsed_from_a_dict(lines: list[str]) -> None:
        # Without the data as the server sent it, the hash is computed over the
        # data serialized again, which only matches for data that Python writes
        # like the server does, such as that of the second event.
        event = Event.parse(json.loads(lines[1])['payload'])

        event.verify_hash()

    @staticmethod
    @pytest.mark.asyncio
    async def test_fails_if_a_trace_field_of_an_event_with_a_hash_of_version_2_was_changed() -> None:
        # Unlike version 1, version 2 also covers traceparent and tracestate.
        events = await read_events_from(
            [line.replace('foo=bar', 'foo=baz') for line in READ_EVENTS_WITH_HASH_V2]
        )

        events[0].verify_hash()
        with pytest.raises(ValidationError, match='Failed to verify hash.'):
            events[1].verify_hash()

    @staticmethod
    @pytest.mark.asyncio
    async def test_fails_with_the_version_if_the_hash_is_of_an_unknown_version() -> None:
        events = await read_events_from(
            [line.replace('esdb:hash:v2:', 'esdb:hash:v3:') for line in READ_EVENTS_WITH_HASH_V2]
        )

        for event in events:
            with pytest.raises(UnsupportedHashVersionError, match="Hash version 'v3' is not supported.") as error:
                event.verify_hash()

            assert error.value.version == 'v3'
            assert isinstance(error.value, ValidationError)
