import pytest_asyncio
from eventsourcingdb.client import Client
from eventsourcingdb.event.event_candidate import EventCandidate
from eventsourcingdb.event.source import Source
from eventsourcingdb.http_client.http_client import HttpClient
from .shared.database import Database
from .shared.start_local_http_server import \
    start_local_http_server, \
    StopServer

pytest_plugins = ('pytest_asyncio', )


@pytest_asyncio.fixture
async def get_http_client():
    stop_server: StopServer | None = None
    client: Client | None = None

    async def getter(attach_handlers) -> HttpClient:
        nonlocal stop_server
        nonlocal client
        client, stop_server = await start_local_http_server(attach_handlers)
        return client.http_client

    yield getter

    if stop_server is not None:
        stop_server()

    if client is not None:
        await client.close()


@pytest_asyncio.fixture
async def database():
    testing_db = await Database.create()
    yield testing_db

    if testing_db is not None:
        await testing_db.stop()


@pytest_asyncio.fixture
async def get_client():
    stop_server: StopServer | None = None
    client: Client | None = None

    async def getter(attach_handlers) -> Client:
        nonlocal stop_server
        nonlocal client
        client, stop_server = await start_local_http_server(attach_handlers)
        return client

    yield getter

    if stop_server is not None:
        stop_server()

    if client is not None:
        await client.close()


class TestData:
    TEST_SOURCE_STRING = 'tag:thenativeweb.io,2023:eventsourcingdb:test'
    TEST_SOURCE = Source(TEST_SOURCE_STRING)
    REGISTERED_SUBJECT = '/users/registered'
    LOGGED_IN_SUBJECT = '/users/logged-in'
    REGISTERED_TYPE = 'io.thenativeweb.users.registered'
    LOGGED_IN_TYPE = 'io.thenativeweb.users.loggedIn'
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
    await database.with_authorization.client.write_events([
        test_data.TEST_SOURCE.new_event(
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JANE_DATA,
            test_data.TRACE_PARENT_1,
            None
        ),
        test_data.TEST_SOURCE.new_event(
            test_data.LOGGED_IN_SUBJECT,
            test_data.LOGGED_IN_TYPE,
            test_data.JANE_DATA,
            test_data.TRACE_PARENT_2,
            None
        ),
        test_data.TEST_SOURCE.new_event(
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_3,
            None
        ),
        test_data.TEST_SOURCE.new_event(
            test_data.LOGGED_IN_SUBJECT,
            test_data.LOGGED_IN_TYPE,
            test_data.JOHN_DATA,
            test_data.TRACE_PARENT_4,
            None
        ),
    ])

    return database


@pytest_asyncio.fixture
async def events_for_mocked_server(
    # This is required in order to request a fixture defined in the same file
    # pylint: disable=redefined-outer-name
    test_data: TestData
    # pylint: enable=redefined-outer-name
) -> list[EventCandidate]:
    return [
        test_data.TEST_SOURCE.new_event('/', 'com.foo.bar', {}, None, None),
    ]
