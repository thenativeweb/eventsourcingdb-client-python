import json
from typing import Any

import pytest
from aiohttp import ClientConnectorDNSError, web

from eventsourcingdb import (
    EventCandidate,
    ReadSubjectsOptions,
    ServerError,
    ValidationError,
)

from .conftest import TestData
from .shared.database import Database
from .shared.stream_server import StreamServer

RECURSIVE = ReadSubjectsOptions(recursive=True)
NOT_RECURSIVE = ReadSubjectsOptions(recursive=False)


async def write_events_to_subjects(client: Any, test_data: TestData, subjects: list[str]) -> None:
    await client.write_events(
        [
            EventCandidate(
                test_data.TEST_SOURCE_STRING,
                subject,
                "io.thenativeweb.user.janeDoe.loggedIn",
                {},
            )
            for subject in subjects
        ]
    )


class TestReadSubjects:
    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_is_not_reachable(database: Database) -> None:
        client = database.get_client("with_invalid_url")

        with pytest.raises(ClientConnectorDNSError):
            async for _ in client.read_subjects("/", RECURSIVE):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_supports_authorization(database: Database) -> None:
        client = database.get_client()

        async for _ in client.read_subjects("/", RECURSIVE):
            pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_all_subjects_starting_from_root(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()
        await write_events_to_subjects(client, test_data, ["/foo"])

        actual_subjects = [subject async for subject in client.read_subjects("/", RECURSIVE)]

        assert actual_subjects == ["/", "/foo"]

    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_all_subjects_starting_from_given_subject(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()
        await write_events_to_subjects(client, test_data, ["/foo/bar"])

        actual_subjects = [subject async for subject in client.read_subjects("/foo", RECURSIVE)]

        assert actual_subjects == ["/foo", "/foo/bar"]

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("subject", "expected_subjects"),
        [
            pytest.param("/", ["/"], id="root"),
            pytest.param("/foo", ["/foo"], id="subject with nested subjects"),
            pytest.param("/foo/", ["/foo"], id="subject with a trailing slash"),
            pytest.param("/foo/bar", ["/foo/bar"], id="subject with events"),
            pytest.param("/fo", [], id="prefix of a subject"),
            pytest.param("/nothing", [], id="unknown subject"),
        ],
    )
    async def test_reads_only_the_given_subject_if_not_recursive(
        database: Database,
        test_data: TestData,
        subject: str,
        expected_subjects: list[str],
    ) -> None:
        client = database.get_client()
        await write_events_to_subjects(client, test_data, ["/foo/bar", "/foo/bar/baz", "/foobar"])

        actual_subjects = [
            read_subject async for read_subject in client.read_subjects(subject, NOT_RECURSIVE)
        ]

        assert actual_subjects == expected_subjects

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_an_error_if_subject_malformed(
        database: Database,
        test_data: TestData,
    ) -> None:
        client = database.get_client()
        await write_events_to_subjects(client, test_data, ["/foo/bar"])

        with pytest.raises(ServerError):
            async for _ in client.read_subjects("", RECURSIVE):
                pass


class TestReadSubjectsOptions:
    @staticmethod
    def test_requires_the_recursive_option() -> None:
        with pytest.raises(TypeError, match="recursive"):
            ReadSubjectsOptions()  # type: ignore[call-arg]

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "options",
        [
            pytest.param(None, id="no options"),
            pytest.param({"recursive": True}, id="a dict instead of options"),
            pytest.param(ReadSubjectsOptions(recursive=None), id="recursive is None"),  # type: ignore[arg-type]
            pytest.param(ReadSubjectsOptions(recursive="yes"), id="recursive is not a bool"),  # type: ignore[arg-type]
        ],
    )
    async def test_fails_right_away_without_a_request_if_recursive_is_not_set(
        options: Any,
    ) -> None:
        async with StreamServer(None) as server:
            with pytest.raises(ValidationError, match="recursive option is True or False"):
                server.get_client().read_subjects("/", options)

            assert server.requests == []

    @staticmethod
    @pytest.mark.asyncio
    async def test_fails_without_options() -> None:
        async with StreamServer(None) as server:
            with pytest.raises(TypeError, match="options"):
                server.get_client().read_subjects("/")  # type: ignore[call-arg]

            assert server.requests == []


class TestReadSubjectsOnTheV1Api:
    SUBJECTS = ("/books", "/books/42", "/books/42/chapters")

    @staticmethod
    async def read_subjects_from_v1_server(
        subject: str,
        options: ReadSubjectsOptions,
        listed_subjects: list[str] | None = None,
    ) -> tuple[list[str], StreamServer]:
        async def write_stream(response: web.StreamResponse) -> None:
            for listed_subject in listed_subjects or TestReadSubjectsOnTheV1Api.SUBJECTS:
                line = json.dumps({"type": "subject", "payload": {"subject": listed_subject}})
                await response.write(line.encode("utf-8") + b"\n")

        async with StreamServer(write_stream) as server:
            subjects = [
                read_subject
                async for read_subject in server.get_client().read_subjects(subject, options)
            ]

        return subjects, server

    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_the_subject_recursively_and_keeps_only_the_subject_itself() -> None:
        subjects, server = await TestReadSubjectsOnTheV1Api.read_subjects_from_v1_server(
            "/books", NOT_RECURSIVE
        )

        assert subjects == ["/books"]
        assert [(request.method, request.path) for request in server.requests][-1] == (
            "POST",
            "/api/v1/read-subjects",
        )
        assert json.loads(server.requests[-1].body) == {"baseSubject": "/books"}

    @staticmethod
    @pytest.mark.asyncio
    async def test_keeps_every_subject_if_recursive() -> None:
        subjects, server = await TestReadSubjectsOnTheV1Api.read_subjects_from_v1_server(
            "/books", RECURSIVE
        )

        assert subjects == list(TestReadSubjectsOnTheV1Api.SUBJECTS)
        assert json.loads(server.requests[-1].body) == {"baseSubject": "/books"}

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("subject", "listed_subjects", "expected_subjects"),
        [
            pytest.param("/a/b/", ["/a/b", "/a/b/c"], ["/a/b"], id="trailing slash"),
            pytest.param("//a/b//", ["/a/b", "/a/b/c"], ["/a/b"], id="several slashes"),
            pytest.param("/", ["/", "/a", "/a/b"], ["/"], id="root"),
        ],
    )
    async def test_keeps_the_subject_as_the_server_normalizes_it(
        subject: str, listed_subjects: list[str], expected_subjects: list[str]
    ) -> None:
        # The server lists a subject as a slash followed by the subject without
        # its leading and trailing slashes, as the v2 API reads it.
        subjects, server = await TestReadSubjectsOnTheV1Api.read_subjects_from_v1_server(
            subject, NOT_RECURSIVE, listed_subjects
        )

        assert subjects == expected_subjects
        assert json.loads(server.requests[-1].body) == {"baseSubject": subject}

    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_nothing_if_the_subject_itself_is_not_listed() -> None:
        subjects, _ = await TestReadSubjectsOnTheV1Api.read_subjects_from_v1_server(
            "/books/4", NOT_RECURSIVE
        )

        assert subjects == []
