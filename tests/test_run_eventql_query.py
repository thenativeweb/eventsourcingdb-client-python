import asyncio

from aiohttp import ClientConnectorDNSError
import pytest

from eventsourcingdb.errors.server_error import ServerError
from eventsourcingdb.event.event_candidate import EventCandidate

from .conftest import TestData
from .shared.database import Database
from .shared.event.assert_event import assert_event_equals


class TestRunEventQLQuery:
    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_is_not_reachable(
        database: Database
    ):
        client = database.get_client("with_invalid_url")

        with pytest.raises(ClientConnectorDNSError):
            async for _ in client.run_eventql_query('FROM e IN events PROJECT INTO e'):
                pass

    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_no_rows_if_query_does_not_return_any_rows(
        database: Database
    ):
        client = database.get_client()
        
        did_read_rows = False
        async for _ in client.run_eventql_query('FROM e IN events PROJECT INTO e'):
            did_read_rows = True
        
        assert did_read_rows is False

    @staticmethod
    @pytest.mark.asyncio
    async def test_reads_all_rows_the_query_returns(
        database: Database
    ):
        client = database.get_client()
        
        first_event = EventCandidate(
            source='https://www.eventsourcingdb.io',
            subject='/test',
            type='io.eventsourcingdb.test',
            data={
                'value': 23,
            },
        )
        
        second_event = EventCandidate(
            source='https://www.eventsourcingdb.io',
            subject='/test',
            type='io.eventsourcingdb.test',
            data={
                'value': 42,
            },
        )
        
        await client.write_events([first_event, second_event])
        
        rows_read = []
        async for row in client.run_eventql_query('FROM e IN events PROJECT INTO e'):
            rows_read.append(row)
        
        assert len(rows_read) == 2
        
        first_row = rows_read[0]
        # Use dictionary access instead of attribute access
        assert first_row['id'] == '0'
        assert first_row['data']['value'] == 23
        
        second_row = rows_read[1]
        assert second_row['id'] == '1'
        assert second_row['data']['value'] == 42

