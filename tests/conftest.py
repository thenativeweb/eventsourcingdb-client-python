import pytest_asyncio

from eventsourcingdb_client_python.client import Client
from eventsourcingdb_client_python.http_client.http_client import HttpClient
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
