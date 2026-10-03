import asyncio

import pytest
from aiohttp import ClientConnectorDNSError, web

from eventsourcingdb import EventCandidate

from .conftest import TEST_DEADLINE_SECONDS
from .shared.database import Database
from .shared.stream_server import StreamServer


class TestRunEventQLQuery:
    EXPECTED_ROW_COUNT = 2
    FIRST_EVENT_ID = "0"
    FIRST_EVENT_VALUE = 23
    SECOND_EVENT_ID = "1"
    SECOND_EVENT_VALUE = 42

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_is_not_reachable(database: Database) -> None:
        client = database.get_client("with_invalid_url")

        with pytest.raises(ClientConnectorDNSError):
            async for _ in client.run_eventql_query("FROM e IN events PROJECT INTO e"):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_no_rows_if_query_does_not_return_any_rows(database: Database) -> None:
        client = database.get_client()

        did_read_rows = False
        async for _ in client.run_eventql_query("FROM e IN events PROJECT INTO e"):
            did_read_rows = True

        assert did_read_rows is False

    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_all_rows_the_query_returns(database: Database) -> None:
        client = database.get_client()

        first_event = EventCandidate(
            source="https://www.eventsourcingdb.io",
            subject="/test",
            type="io.eventsourcingdb.test",
            data={
                "value": TestRunEventQLQuery.FIRST_EVENT_VALUE,
            },
        )

        second_event = EventCandidate(
            source="https://www.eventsourcingdb.io",
            subject="/test",
            type="io.eventsourcingdb.test",
            data={
                "value": TestRunEventQLQuery.SECOND_EVENT_VALUE,
            },
        )

        await client.write_events([first_event, second_event])

        rows_read = []
        async for row in client.run_eventql_query("FROM e IN events PROJECT INTO e"):
            rows_read.append(row)

        assert len(rows_read) == TestRunEventQLQuery.EXPECTED_ROW_COUNT

        first_row = rows_read[0]
        assert first_row["id"] == TestRunEventQLQuery.FIRST_EVENT_ID
        assert first_row["data"]["value"] == TestRunEventQLQuery.FIRST_EVENT_VALUE

        second_row = rows_read[1]
        assert second_row["id"] == TestRunEventQLQuery.SECOND_EVENT_ID
        assert second_row["data"]["value"] == TestRunEventQLQuery.SECOND_EVENT_VALUE

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("short_session_timeout")
    async def test_keeps_running_a_query_for_longer_than_the_session_timeout() -> None:
        async def write_stream(response: web.StreamResponse) -> None:
            while True:
                await response.write(b'{"type":"heartbeat","payload":{}}\n')
                await asyncio.sleep(1)

        async with StreamServer(write_stream) as server:
            client = server.get_client()

            with pytest.raises(TimeoutError):
                async with asyncio.timeout(TEST_DEADLINE_SECONDS) as deadline:
                    async for _ in client.run_eventql_query("FROM e IN events PROJECT INTO e"):
                        pass

        assert deadline.expired(), "The query must only end at the deadline of the test."
