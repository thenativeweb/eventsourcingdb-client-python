import logging
import pytest
import pytest_asyncio
from eventsourcingdb import EventCandidate
from .shared.database import Database


@pytest_asyncio.fixture
async def database():
    # pylint: disable=W0717
    try:
        testing_db = await Database.create()
        yield testing_db
    # pylint: disable=broad-except
    except Exception as e:
        logging.error("Failed to create database container: %s", e)
        pytest.skip(f"Skipping test due to database container initialization failure: {e}")
    finally:
        if testing_db in locals() and testing_db is not None:
            await testing_db.stop()


class TestData:
    TEST_SOURCE_STRING = 'tag:thenativeweb.io,2023:eventsourcingdb:test'
    REGISTERED_SUBJECT = '/users/registered'
    LOGGED_IN_SUBJECT = '/users/logged-in'
    REGISTERED_TYPE = 'io.thenativeweb.users.registered'
    LOGGED_IN_TYPE = 'io.thenativeweb.users.logged-in'
    JANE_DATA = {'name': 'jane'}
    JOHN_DATA = {'name': 'john'}
    APFEL_FRED_DATA = {'name': 'apfel fred'}
    TRACE_PARENT_1 = "00-10000000000000000000000000000000-1000000000000000-00"
    TRACE_PARENT_2 = "00-20000000000000000000000000000000-2000000000000000-00"
    TRACE_PARENT_3 = "00-30000000000000000000000000000000-3000000000000000-00"
    TRACE_PARENT_4 = "00-40000000000000000000000000000000-4000000000000000-00"
    TRACE_PARENT_5 = "00-50000000000000000000000000000000-5000000000000000-00"


@pytest_asyncio.fixture
async def test_data() -> TestData:
    return TestData()


@pytest_asyncio.fixture
async def prepared_database(
    # This is required in order to request a fixture defined in the same file
    # pylint: disable=redefined-outer-name
    database: Database,
    test_data: TestData
    # pylint: enable=redefined-outer-name
) -> Database:
    await database.get_client().write_events(
        [
            EventCandidate(
                source=test_data.TEST_SOURCE_STRING,
                subject=test_data.REGISTERED_SUBJECT,
                type=test_data.REGISTERED_TYPE,
                data=test_data.JANE_DATA,
                trace_parent=test_data.TRACE_PARENT_1,
            ),
            EventCandidate(
                source=test_data.TEST_SOURCE_STRING,
                subject=test_data.LOGGED_IN_SUBJECT,
                type=test_data.LOGGED_IN_TYPE,
                data=test_data.JANE_DATA,
                trace_parent=test_data.TRACE_PARENT_2,
            ),
            EventCandidate(
                source=test_data.TEST_SOURCE_STRING,
                subject=test_data.REGISTERED_SUBJECT,
                type=test_data.REGISTERED_TYPE,
                data=test_data.JOHN_DATA,
                trace_parent=test_data.TRACE_PARENT_3,
            ),
            EventCandidate(
                source=test_data.TEST_SOURCE_STRING,
                subject=test_data.LOGGED_IN_SUBJECT,
                type=test_data.LOGGED_IN_TYPE,
                data=test_data.JOHN_DATA,
                trace_parent=test_data.TRACE_PARENT_4,
            )
        ]
    )

    return database


@pytest_asyncio.fixture
async def events_for_mocked_server(
    # This is required in order to request a fixture defined in the same file
    # pylint: disable=redefined-outer-name
    test_data: TestData
    # pylint: enable=redefined-outer-name
) -> list[EventCandidate]:

    return [
        EventCandidate(
            source=test_data.TEST_SOURCE_STRING,
            subject='com.foo.bar',
            type='com.foo.bar',
            data={},
            trace_parent=None,
            trace_state=None
        )
    ]
