from datetime import datetime

import pandas as pd
import pytest

from eventsourcingdb import EventCandidate, ReadEventsOptions
from eventsourcingdb.pandas import events_to_dataframe

from .conftest import TestData
from .shared.database import Database


class TestEventsToDataframe:
    @staticmethod
    @pytest.mark.asyncio
    async def test_returns_empty_dataframe_for_empty_event_stream(
        database: Database,
    ) -> None:
        client = database.get_client()

        events = client.read_events("/nonexistent", ReadEventsOptions(recursive=False))
        df = await events_to_dataframe(events)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert list(df.columns) == [
            "event_id",
            "time",
            "source",
            "subject",
            "type",
            "data",
            "spec_version",
            "data_content_type",
            "predecessor_hash",
            "hash",
            "trace_parent",
            "trace_state",
            "signature",
        ]

    @staticmethod
    @pytest.mark.asyncio
    async def test_returns_dataframe_with_single_event(
        database: Database, test_data: TestData
    ) -> None:
        client = database.get_client()

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING,
                    subject=test_data.REGISTERED_SUBJECT,
                    type=test_data.REGISTERED_TYPE,
                    data=test_data.JANE_DATA,
                    trace_parent=test_data.TRACE_PARENT_1,
                )
            ]
        )

        events = client.read_events(
            test_data.REGISTERED_SUBJECT, ReadEventsOptions(recursive=False)
        )
        df = await events_to_dataframe(events)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1

        assert df.iloc[0]["source"] == test_data.TEST_SOURCE_STRING
        assert df.iloc[0]["subject"] == test_data.REGISTERED_SUBJECT
        assert df.iloc[0]["type"] == test_data.REGISTERED_TYPE
        assert df.iloc[0]["data"] == test_data.JANE_DATA
        assert df.iloc[0]["trace_parent"] == test_data.TRACE_PARENT_1

    @staticmethod
    @pytest.mark.asyncio
    async def test_returns_dataframe_with_multiple_events(
        prepared_database: Database, test_data: TestData
    ) -> None:
        client = prepared_database.get_client()

        events = client.read_events("/users", ReadEventsOptions(recursive=True))
        df = await events_to_dataframe(events)

        assert isinstance(df, pd.DataFrame)
        expected_event_count = 4
        assert len(df) == expected_event_count

        assert df.iloc[0]["data"] == test_data.JANE_DATA
        assert df.iloc[1]["data"] == test_data.JANE_DATA
        assert df.iloc[2]["data"] == test_data.JOHN_DATA
        assert df.iloc[3]["data"] == test_data.JOHN_DATA

    @staticmethod
    @pytest.mark.asyncio
    async def test_dataframe_has_correct_column_names(
        database: Database, test_data: TestData
    ) -> None:
        client = database.get_client()

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING,
                    subject=test_data.REGISTERED_SUBJECT,
                    type=test_data.REGISTERED_TYPE,
                    data=test_data.JANE_DATA,
                )
            ]
        )

        events = client.read_events(
            test_data.REGISTERED_SUBJECT, ReadEventsOptions(recursive=False)
        )
        df = await events_to_dataframe(events)

        expected_columns = [
            "event_id",
            "time",
            "source",
            "subject",
            "type",
            "data",
            "spec_version",
            "data_content_type",
            "predecessor_hash",
            "hash",
            "trace_parent",
            "trace_state",
            "signature",
        ]
        assert list(df.columns) == expected_columns

    @staticmethod
    @pytest.mark.asyncio
    async def test_data_field_remains_as_dict(
        database: Database, test_data: TestData
    ) -> None:
        client = database.get_client()

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING,
                    subject=test_data.REGISTERED_SUBJECT,
                    type=test_data.REGISTERED_TYPE,
                    data=test_data.JANE_DATA,
                )
            ]
        )

        events = client.read_events(
            test_data.REGISTERED_SUBJECT, ReadEventsOptions(recursive=False)
        )
        df = await events_to_dataframe(events)

        assert isinstance(df.iloc[0]["data"], dict)
        assert df.iloc[0]["data"] == test_data.JANE_DATA

    @staticmethod
    @pytest.mark.asyncio
    async def test_time_field_is_datetime_object(
        database: Database, test_data: TestData
    ) -> None:
        client = database.get_client()

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING,
                    subject=test_data.REGISTERED_SUBJECT,
                    type=test_data.REGISTERED_TYPE,
                    data=test_data.JANE_DATA,
                )
            ]
        )

        events = client.read_events(
            test_data.REGISTERED_SUBJECT, ReadEventsOptions(recursive=False)
        )
        df = await events_to_dataframe(events)

        assert isinstance(df.iloc[0]["time"], datetime)

    @staticmethod
    @pytest.mark.asyncio
    async def test_optional_fields_can_be_none(
        database: Database, test_data: TestData
    ) -> None:
        client = database.get_client()

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING,
                    subject=test_data.REGISTERED_SUBJECT,
                    type=test_data.REGISTERED_TYPE,
                    data=test_data.JANE_DATA,
                )
            ]
        )

        events = client.read_events(
            test_data.REGISTERED_SUBJECT, ReadEventsOptions(recursive=False)
        )
        df = await events_to_dataframe(events)

        assert df.iloc[0]["trace_parent"] is None or pd.isna(df.iloc[0]["trace_parent"])
        assert df.iloc[0]["trace_state"] is None or pd.isna(df.iloc[0]["trace_state"])
        assert df.iloc[0]["signature"] is None or pd.isna(df.iloc[0]["signature"])

    @staticmethod
    @pytest.mark.asyncio
    async def test_all_event_fields_are_present(
        database: Database, test_data: TestData
    ) -> None:
        client = database.get_client()

        await client.write_events(
            [
                EventCandidate(
                    source=test_data.TEST_SOURCE_STRING,
                    subject=test_data.REGISTERED_SUBJECT,
                    type=test_data.REGISTERED_TYPE,
                    data=test_data.JANE_DATA,
                    trace_parent=test_data.TRACE_PARENT_1,
                )
            ]
        )

        events = client.read_events(
            test_data.REGISTERED_SUBJECT, ReadEventsOptions(recursive=False)
        )
        df = await events_to_dataframe(events)

        row = df.iloc[0]

        assert isinstance(row["event_id"], str)
        assert isinstance(row["time"], datetime)
        assert row["source"] == test_data.TEST_SOURCE_STRING
        assert row["subject"] == test_data.REGISTERED_SUBJECT
        assert row["type"] == test_data.REGISTERED_TYPE
        assert row["data"] == test_data.JANE_DATA
        assert isinstance(row["spec_version"], str)
        assert isinstance(row["data_content_type"], str)
        assert isinstance(row["predecessor_hash"], str)
        assert isinstance(row["hash"], str)
        assert row["trace_parent"] == test_data.TRACE_PARENT_1
