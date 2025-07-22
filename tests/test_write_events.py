from aiohttp import ClientConnectorDNSError
import pytest

from eventsourcingdb import ServerError
from eventsourcingdb import EventCandidate
from eventsourcingdb import IsSubjectPristine, IsSubjectOnEventId
from eventsourcingdb.write_events.preconditions import IsEventQlTrue

from .conftest import TestData

from .shared.database import Database


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
                        subject='/',
                        type='com.foo.bar',
                        data={}
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
                        source=test_data.TEST_SOURCE_STRING,
                        subject='',
                        type='com.foo.bar',
                        data={}
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
                [
                    EventCandidate(
                        source=test_data.TEST_SOURCE_STRING,
                        subject='/',
                        type='',
                        data={}
                    )
                ]
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
                    source=test_data.TEST_SOURCE_STRING,
                    subject='/',
                    type='com.foo.bar',
                    data={}
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
                    source=test_data.TEST_SOURCE_STRING,
                    subject='/',
                    type='com.foo.bar',
                    data={}
                )
            ],
            [IsSubjectPristine('/')]
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
                    source=test_data.TEST_SOURCE_STRING,
                    subject='/',
                    type='com.foo.bar',
                    data={}
                )
            ]
        )

        with pytest.raises(ServerError):
            await client.write_events(
                [
                    EventCandidate(
                        source=test_data.TEST_SOURCE_STRING,
                        subject='/',
                        type='com.foo.bar',
                        data={}
                    )
                ],
                [IsSubjectPristine('/')]
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
                    source=test_data.TEST_SOURCE_STRING,
                    subject='/',
                    type='com.foo.bar',
                    data={}
                )
            ]
        )

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING,
                    subject='/',
                    type='com.foo.bar',
                    data={}
                )
            ],
            [IsSubjectOnEventId('/', '0')]
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
                    source=test_data.TEST_SOURCE_STRING,
                    subject='/',
                    type='com.foo.bar',
                    data={}
                )
            ]
        )

        with pytest.raises(ServerError):
            await client.write_events(
                [
                    EventCandidate(
                        source=test_data.TEST_SOURCE_STRING,
                        subject='/',
                        type='com.foo.bar',
                        data={}
                    )
                ],
                [IsSubjectOnEventId('/', '2')]
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
                    source=test_data.TEST_SOURCE_STRING,
                    subject='/',
                    type='com.foo.bar',
                    data={}
                )
            ]
        )

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING,
                    subject='/',
                    type='com.foo.bar',
                    data={}
                )
            ],
            [IsEventQlTrue('FROM e IN events PROJECT INTO COUNT() > 0')]
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
                    source=test_data.TEST_SOURCE_STRING,
                    subject='/',
                    type='com.foo.bar',
                    data={}
                )
            ]
        )

        with pytest.raises(ServerError):
            await client.write_events(
                [
                    EventCandidate(
                        source=test_data.TEST_SOURCE_STRING,
                        subject='/',
                        type='com.foo.bar',
                        data={}
                    )
                ],
                [IsEventQlTrue('FROM e IN events PROJECT INTO COUNT() == 0')]
            )

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_event_does_not_match_schema(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        await client.register_event_schema(
            "com.super.duper",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False
            }
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
