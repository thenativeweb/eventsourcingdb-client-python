import asyncio
import json

import pytest
from aiohttp import ClientConnectorDNSError, web

from eventsourcingdb import (
    Client,
    ConnectionStalledError,
    CustomError,
    DbApiError,
    ErrorCode,
    EventCandidate,
    IncompatibleServerError,
    IsEventQlQueryTrue,
    IsSubjectOnEventId,
    IsSubjectPopulated,
    IsSubjectPristine,
    OutcomeUnknownError,
    Precondition,
    PreconditionOptions,
    ReadEventsOptions,
    ServerError,
)

from .conftest import STALL_TIMEOUT_SECONDS, TEST_DEADLINE_SECONDS, TestData
from .event.fixtures import WRITTEN_EVENTS_WITH_HASH_V2
from .shared.database import Database
from .shared.stream_server import StreamServer

RECURSIVE = PreconditionOptions(recursive=True)
NOT_RECURSIVE = PreconditionOptions(recursive=False)

# Events 0 and 1 are written below /books, but none to /books itself, and none
# to /authors or below it, so that each precondition on a subject holds or is
# violated depending on whether it is recursive.
SUBJECTS_OF_WRITTEN_EVENTS = ["/books/42", "/books/42/chapters/1"]
IDS_OF_WRITTEN_EVENTS = ["0", "1"]

RECURSIVE_PRECONDITIONS_THAT_HOLD = [
    pytest.param(IsSubjectPristine("/authors", RECURSIVE), id="isSubjectPristine"),
    pytest.param(IsSubjectPopulated("/books", RECURSIVE), id="isSubjectPopulated"),
    pytest.param(IsSubjectOnEventId("/books/42", "1", RECURSIVE), id="isSubjectOnEventId"),
]
RECURSIVE_PRECONDITIONS_THAT_ARE_VIOLATED = [
    pytest.param(IsSubjectPristine("/books", RECURSIVE), id="isSubjectPristine"),
    pytest.param(IsSubjectPopulated("/authors", RECURSIVE), id="isSubjectPopulated"),
    pytest.param(IsSubjectOnEventId("/books/42", "0", RECURSIVE), id="isSubjectOnEventId"),
]
PRECONDITIONS_THAT_ARE_NOT_RECURSIVE_AND_HOLD = [
    pytest.param(IsSubjectPristine("/books", NOT_RECURSIVE), id="isSubjectPristine"),
    pytest.param(IsSubjectPopulated("/books/42", NOT_RECURSIVE), id="isSubjectPopulated"),
    pytest.param(IsSubjectOnEventId("/books/42", "0", NOT_RECURSIVE), id="isSubjectOnEventId"),
]
PRECONDITIONS_THAT_ARE_NOT_RECURSIVE_AND_VIOLATED = [
    pytest.param(IsSubjectPristine("/books/42", NOT_RECURSIVE), id="isSubjectPristine"),
    pytest.param(IsSubjectPopulated("/books", NOT_RECURSIVE), id="isSubjectPopulated"),
    pytest.param(IsSubjectOnEventId("/books/42", "1", NOT_RECURSIVE), id="isSubjectOnEventId"),
]


def event_candidate(test_data: TestData, subject: str) -> EventCandidate:
    return EventCandidate(
        source=test_data.TEST_SOURCE_STRING,
        subject=subject,
        type="com.foo.bar",
        data={},
    )


async def write_events_below_books(client: Client, test_data: TestData) -> None:
    await client.write_events(
        [event_candidate(test_data, subject) for subject in SUBJECTS_OF_WRITTEN_EVENTS]
    )


async def write_event_with(
    client: Client, test_data: TestData, precondition: Precondition
) -> None:
    await client.write_events([event_candidate(test_data, "/books/42")], [precondition])


async def read_ids_of_all_events(client: Client) -> list[str]:
    return [
        event.event_id
        async for event in client.read_events("/", ReadEventsOptions(recursive=True))
    ]


class TestWriteSubjects:
    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_an_error_if_server_is_not_reachable(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client("with_invalid_url")

        with pytest.raises(ClientConnectorDNSError):
            await client.write_events(
                [
                    EventCandidate(
                        source=test_data.TEST_SOURCE_STRING,
                        subject="/",
                        type="com.foo.bar",
                        data={},
                    )
                ]
            )

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_an_error_for_empty_event_candidates(
        database: Database,
    ) -> None:
        client = database.get_client("with_invalid_url")

        with pytest.raises(ClientConnectorDNSError):
            await client.write_events([])

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_an_error_for_malformed_subject(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        with pytest.raises(ServerError):
            await client.write_events(
                [
                    EventCandidate(
                        source=test_data.TEST_SOURCE_STRING, subject="", type="com.foo.bar", data={}
                    )
                ]
            )

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_an_error_for_malformed_type(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        with pytest.raises(ServerError):
            await client.write_events(
                [EventCandidate(source=test_data.TEST_SOURCE_STRING, subject="/", type="", data={})]
            )

    @staticmethod
    @pytest.mark.asyncio
    async def test_supports_authorization(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING, subject="/", type="com.foo.bar", data={}
                )
            ]
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_is_pristine_precondition_works_for_new_subject(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING, subject="/", type="com.foo.bar", data={}
                )
            ],
            [IsSubjectPristine("/")],
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_is_pristine_precondition_fails_for_existing_subject(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING, subject="/", type="com.foo.bar", data={}
                )
            ]
        )

        with pytest.raises(ServerError):
            await client.write_events(
                [
                    EventCandidate(
                        source=test_data.TEST_SOURCE_STRING,
                        subject="/",
                        type="com.foo.bar",
                        data={},
                    )
                ],
                [IsSubjectPristine("/")],
            )

    @staticmethod
    @pytest.mark.asyncio
    async def test_is_subject_populated_precondition_fails_for_empty_subject(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        with pytest.raises(ServerError):
            await client.write_events(
                [
                    EventCandidate(
                        source=test_data.TEST_SOURCE_STRING,
                        subject="/",
                        type="com.foo.bar",
                        data={},
                    )
                ],
                [IsSubjectPopulated("/")],
            )

    @staticmethod
    @pytest.mark.asyncio
    async def test_is_subject_populated_precondition_works_for_existing_subject(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING,
                    subject="/",
                    type="com.foo.bar",
                    data={"value": 23},
                )
            ]
        )

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING,
                    subject="/",
                    type="com.foo.bar",
                    data={"value": 42},
                )
            ],
            [IsSubjectPopulated("/")],
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_is_on_event_id_precondition_works_for_correct_id(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING, subject="/", type="com.foo.bar", data={}
                )
            ]
        )

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING, subject="/", type="com.foo.bar", data={}
                )
            ],
            [IsSubjectOnEventId("/", "0")],
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_is_subject_on_event_id_fails_for_wrong_id(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING, subject="/", type="com.foo.bar", data={}
                )
            ]
        )

        with pytest.raises(ServerError):
            await client.write_events(
                [
                    EventCandidate(
                        source=test_data.TEST_SOURCE_STRING,
                        subject="/",
                        type="com.foo.bar",
                        data={},
                    )
                ],
                [IsSubjectOnEventId("/", "2")],
            )

    @staticmethod
    @pytest.mark.asyncio
    async def test_is_event_ql_true_precondition_works(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING, subject="/", type="com.foo.bar", data={}
                )
            ]
        )

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING, subject="/", type="com.foo.bar", data={}
                )
            ],
            [IsEventQlQueryTrue("FROM e IN events PROJECT INTO COUNT() > 0")]
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_is_event_ql_true_precondition_fails(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING, subject="/", type="com.foo.bar", data={}
                )
            ]
        )

        with pytest.raises(ServerError):
            await client.write_events(
                [
                    EventCandidate(
                        source=test_data.TEST_SOURCE_STRING,
                        subject="/",
                        type="com.foo.bar",
                        data={},
                    )
                ],
                [IsEventQlQueryTrue("FROM e IN events PROJECT INTO COUNT() == 0")]
            )

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_event_does_not_match_schema(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        await client.register_event_schema(
            "com.super.duper", {"type": "object", "properties": {}, "additionalProperties": False}
        )

        with pytest.raises(ServerError):
            await client.write_events(
                [
                    EventCandidate(
                        source=test_data.TEST_SOURCE_STRING,
                        subject="/",
                        type="com.super.duper",
                        data={
                            "haft": "befehl",
                        },
                    ),
                ]
            )

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_an_error_if_server_stalls_for_longer_than_the_stall_timeout(
        test_data: TestData,
    ) -> None:
        async def write_stream(_: web.StreamResponse) -> None:
            await asyncio.Event().wait()

        async with StreamServer(write_stream, stall_timeout=STALL_TIMEOUT_SECONDS) as server:
            client = server.get_client()

            with pytest.raises(OutcomeUnknownError) as error:
                async with asyncio.timeout(TEST_DEADLINE_SECONDS) as deadline:
                    await client.write_events(
                        [
                            EventCandidate(
                                source=test_data.TEST_SOURCE_STRING,
                                subject="/",
                                type="com.foo.bar",
                                data={},
                            )
                        ]
                    )

        assert not deadline.expired(), (
            "The stall timeout must end the request before the deadline of the test does."
        )
        # Since the server may have stored the events, their outcome is unknown.
        assert isinstance(error.value.cause, ConnectionStalledError)


class TestPreconditionsOnASubject:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("precondition", RECURSIVE_PRECONDITIONS_THAT_HOLD)
    async def test_writes_if_a_recursive_precondition_holds_for_the_subject_and_below_it(
        database: Database,
        test_data: TestData,
        precondition: Precondition,
    ) -> None:
        client = database.get_client()
        await write_events_below_books(client, test_data)

        if await database.offers_v2_api():
            await write_event_with(client, test_data, precondition)

            assert await read_ids_of_all_events(client) == [*IDS_OF_WRITTEN_EVENTS, "2"]
        else:
            with pytest.raises(IncompatibleServerError):
                await write_event_with(client, test_data, precondition)

            assert await read_ids_of_all_events(client) == IDS_OF_WRITTEN_EVENTS

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("precondition", RECURSIVE_PRECONDITIONS_THAT_ARE_VIOLATED)
    async def test_refuses_to_write_if_a_recursive_precondition_is_violated(
        database: Database,
        test_data: TestData,
        precondition: Precondition,
    ) -> None:
        client = database.get_client()
        await write_events_below_books(client, test_data)

        if await database.offers_v2_api():
            with pytest.raises(DbApiError) as error:
                await write_event_with(client, test_data, precondition)

            assert error.value.code == ErrorCode.PRECONDITION_VIOLATED
        else:
            with pytest.raises(IncompatibleServerError):
                await write_event_with(client, test_data, precondition)

        assert await read_ids_of_all_events(client) == IDS_OF_WRITTEN_EVENTS

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("precondition", PRECONDITIONS_THAT_ARE_NOT_RECURSIVE_AND_HOLD)
    async def test_writes_if_a_precondition_that_is_not_recursive_holds_for_the_subject_alone(
        database: Database,
        test_data: TestData,
        precondition: Precondition,
    ) -> None:
        client = database.get_client()
        await write_events_below_books(client, test_data)

        await write_event_with(client, test_data, precondition)

        assert await read_ids_of_all_events(client) == [*IDS_OF_WRITTEN_EVENTS, "2"]

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("precondition", PRECONDITIONS_THAT_ARE_NOT_RECURSIVE_AND_VIOLATED)
    async def test_refuses_to_write_if_a_precondition_that_is_not_recursive_is_violated(
        database: Database,
        test_data: TestData,
        precondition: Precondition,
    ) -> None:
        client = database.get_client()
        await write_events_below_books(client, test_data)

        with pytest.raises(DbApiError) as error:
            await write_event_with(client, test_data, precondition)

        assert error.value.code == ErrorCode.PRECONDITION_VIOLATED
        assert await read_ids_of_all_events(client) == IDS_OF_WRITTEN_EVENTS


class TestPreconditionsOnASubjectOnTheV1Api:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("precondition", RECURSIVE_PRECONDITIONS_THAT_HOLD)
    async def test_fails_without_sending_the_write_if_a_precondition_is_recursive(
        test_data: TestData,
        precondition: Precondition,
    ) -> None:
        async def write_stream(response: web.StreamResponse) -> None:
            await response.write(WRITTEN_EVENTS_WITH_HASH_V2.encode("utf-8"))

        async with StreamServer(write_stream) as server:
            with pytest.raises(IncompatibleServerError) as error:
                await server.get_client().write_events(
                    [event_candidate(test_data, "/books/42")],
                    [IsSubjectPristine("/books/23"), precondition],
                )

            assert server.requests == []

        assert isinstance(error.value, CustomError)
        assert str(error.value) == (
            "The server does not offer the v2 API, which a recursive precondition needs."
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_sends_preconditions_whose_options_are_not_recursive_as_without_options(
        test_data: TestData,
    ) -> None:
        async def write_stream(response: web.StreamResponse) -> None:
            await response.write(WRITTEN_EVENTS_WITH_HASH_V2.encode("utf-8"))

        async with StreamServer(write_stream) as server:
            await server.get_client().write_events(
                [event_candidate(test_data, "/books/42")],
                [
                    IsSubjectPristine("/books", NOT_RECURSIVE),
                    IsSubjectPopulated("/books", NOT_RECURSIVE),
                    IsSubjectOnEventId("/books", "0", NOT_RECURSIVE),
                ],
            )

            [request] = server.requests
            assert (request.method, request.path) == ("POST", "/api/v1/write-events")
            assert json.loads(request.body)["preconditions"] == [
                {"type": "isSubjectPristine", "payload": {"subject": "/books"}},
                {"type": "isSubjectPopulated", "payload": {"subject": "/books"}},
                {"type": "isSubjectOnEventId", "payload": {"subject": "/books", "eventId": "0"}},
            ]
