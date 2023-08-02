import pytest_asyncio

from eventsourcingdb_client_python.client import Client
from eventsourcingdb_client_python.event.source import Source
from eventsourcingdb_client_python.http_client.http_client import HttpClient
from .shared.database import Database
from .shared.event.test_source import TEST_SOURCE

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
    test_source = Source(TEST_SOURCE)
    REGISTERED_SUBJECT = '/users/registered'
    LOGGED_IN_SUBJECT = '/users/loggedIn'
    REGISTERED_TYPE = 'io.thenativeweb.users.registered'
    LOGGED_IN_TYPE = 'io.thenativeweb.users.loggedIn'
    JANE_DATA = {'name': 'jane'}
    JOHN_DATA = {'name': 'john'}
    APFEL_FRED_DATA = {'name': 'apfel fred'}


@pytest_asyncio.fixture
async def test_data() -> TestData:
    return TestData()


@pytest_asyncio.fixture
async def prepared_database(database: Database, test_data: TestData) -> Database:
    await database.with_authorization.client.write_events([
        test_data.test_source.new_event(
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JANE_DATA
        ),
        test_data.test_source.new_event(
            test_data.LOGGED_IN_SUBJECT,
            test_data.LOGGED_IN_TYPE,
            test_data.JANE_DATA
        ),
        test_data.test_source.new_event(
            test_data.REGISTERED_SUBJECT,
            test_data.REGISTERED_TYPE,
            test_data.JOHN_DATA
        ),
        test_data.test_source.new_event(
            test_data.LOGGED_IN_SUBJECT,
            test_data.LOGGED_IN_TYPE,
            test_data.JOHN_DATA
        ),
    ])

    return database
