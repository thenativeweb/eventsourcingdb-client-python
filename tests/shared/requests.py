from collections.abc import Awaitable, Callable

import pytest

from eventsourcingdb import (
    Client,
    EventCandidate,
    ObserveEventsOptions,
    ReadEventsOptions,
    ReadSubjectsOptions,
)

# Each of the calls of the client, as a function that makes it and consumes
# whatever it returns, so that tests can run all of them the same way.
Request = Callable[[Client], Awaitable[None]]


async def ping(client: Client) -> None:
    await client.ping()


async def verify_api_token(client: Client) -> None:
    await client.verify_api_token()


async def write_events(client: Client) -> None:
    await client.write_events(
        [
            EventCandidate(
                source='https://www.eventsourcingdb.io',
                subject='/books/42',
                type='io.eventsourcingdb.library.book-acquired',
                data={},
            )
        ]
    )


async def register_event_schema(client: Client) -> None:
    await client.register_event_schema(
        'io.eventsourcingdb.library.book-acquired', {'type': 'object'}
    )


async def read_event_type(client: Client) -> None:
    await client.read_event_type('io.eventsourcingdb.library.book-acquired')


async def read_events(client: Client) -> None:
    async for _ in client.read_events('/', ReadEventsOptions(recursive=True)):
        pass


async def read_subjects(client: Client) -> None:
    async for _ in client.read_subjects('/', ReadSubjectsOptions(recursive=True)):
        pass


async def read_event_types(client: Client) -> None:
    async for _ in client.read_event_types():
        pass


async def observe_events(client: Client) -> None:
    async for _ in client.observe_events('/', ObserveEventsOptions(recursive=True)):
        pass


async def observe_first_event(client: Client) -> None:
    # Observing never ends, so a request that is complete stops at an event.
    async for _ in client.observe_events('/', ObserveEventsOptions(recursive=True)):
        break


async def run_eventql_query(client: Client) -> None:
    async for _ in client.run_eventql_query('FROM e IN events PROJECT INTO e'):
        pass


ONE_SHOT_REQUESTS = [
    pytest.param(ping, id='ping'),
    pytest.param(verify_api_token, id='verify_api_token'),
    pytest.param(write_events, id='write_events'),
    pytest.param(register_event_schema, id='register_event_schema'),
    pytest.param(read_event_type, id='read_event_type'),
]
STREAMS = [
    pytest.param(read_events, id='read_events'),
    pytest.param(read_subjects, id='read_subjects'),
    pytest.param(read_event_types, id='read_event_types'),
]
HEARTBEAT_STREAMS = [
    pytest.param(observe_events, id='observe_events'),
    pytest.param(run_eventql_query, id='run_eventql_query'),
]
ALL_REQUESTS = ONE_SHOT_REQUESTS + STREAMS + HEARTBEAT_STREAMS
WRITES = [
    pytest.param(write_events, id='write_events'),
    pytest.param(register_event_schema, id='register_event_schema'),
]
