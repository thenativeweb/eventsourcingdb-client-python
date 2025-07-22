import pytest
from aiohttp import ClientConnectorDNSError

from eventsourcingdb import EventCandidate, ServerError

from .conftest import TestData
from .shared.database import Database


class TestReadSubjects:
    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_is_not_reachable(database: Database) -> None:
        client = database.get_client("with_invalid_url")

        with pytest.raises(ClientConnectorDNSError):
            async for _ in client.read_subjects("/"):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_supports_authorization(database: Database) -> None:
        client = database.get_client()

        async for _ in client.read_subjects("/"):
            pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_all_subjects_starting_from_root(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        await client.write_events(
            [
                EventCandidate(
                    test_data.TEST_SOURCE_STRING,
                    "/foo",
                    "io.thenativeweb.user.janeDoe.loggedIn",
                    {},
                )
            ]
        )

        actual_subjects = []
        async for subject in client.read_subjects("/"):
            actual_subjects.append(subject)

        assert actual_subjects == ["/", "/foo"]

    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_all_subjects_starting_from_given_base_subject(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        await client.write_events(
            [
                EventCandidate(
                    test_data.TEST_SOURCE_STRING,
                    "/foo/bar",
                    "io.thenativeweb.user.janeDoe.loggedIn",
                    {},
                )
            ]
        )

        actual_subjects = []
        async for subject in client.read_subjects("/foo"):
            actual_subjects.append(subject)

        assert actual_subjects == ["/foo", "/foo/bar"]

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_an_error_if_base_subject_malformed(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()

        await client.write_events(
            [
                EventCandidate(
                    test_data.TEST_SOURCE_STRING,
                    "/foo/bar",
                    "io.thenativeweb.user.janeDoe.loggedIn",
                    {},
                )
            ]
        )

        with pytest.raises(ServerError):
            async for _ in client.read_subjects(""):
                pass
