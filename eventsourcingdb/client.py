from collections.abc import AsyncGenerator
import contextlib
from types import TracebackType
from typing import TypeVar

from .abstract_base_client import AbstractBaseClient
from .event.event import Event
from .event.event_candidate import EventCandidate
from .event.event_context import EventContext
from .handlers.observe_events.observe_events import observe_events
from .handlers.observe_events.observe_events_options import ObserveEventsOptions
from .handlers.read_event_types.event_type import EventType
from .handlers.read_event_types.read_event_types import read_event_types
from .handlers.register_event_schema.register_event_schema import register_event_schema
from .http_client.http_client import HttpClient
from .handlers.ping import ping
from .handlers.read_events import read_events, ReadEventsOptions
from .handlers.read_subjects import read_subjects
from .handlers.write_events import Precondition, write_events


T = TypeVar('T')


class Client(AbstractBaseClient):
    def __init__(
        self,
        base_url: str,
        api_token: str,
    ):
        self.__http_client = HttpClient(base_url=base_url, api_token=api_token)

    async def __aenter__(self):
        await self.__http_client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: BaseException | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        await self.__http_client.__aexit__(exc_type, exc_val, exc_tb)

    async def initialize(self) -> None:
        await self.__http_client.initialize()

    async def close(self) -> None:
        await self.__http_client.close()

    @property
    def http_client(self) -> HttpClient:
        return self.__http_client

    async def ping(self) -> None:
        return await ping(self)

    async def verify_api_token(self) -> None:
        raise NotImplementedError("verify_api_token is not implemented yet.")

    async def write_events(
        self,
        event_candidates: list[EventCandidate],
        preconditions: list[Precondition] = None  # type: ignore
    ) -> list[EventContext]:
        if preconditions is None:
            preconditions = []
        return await write_events(self, event_candidates, preconditions)

    async def read_events(
        self,
        subject: str,
        options: ReadEventsOptions
    ) -> AsyncGenerator[Event]:
        async with contextlib.aclosing(read_events(self, subject, options)) as generator:
            async for item in generator:
                yield item

    async def run_eventql_query(self, query: str) -> AsyncGenerator[Event]:
        raise NotImplementedError("run_eventql_query is not implemented yet.")

    async def observe_events(
        self,
        subject: str,
        options: ObserveEventsOptions
    ) -> AsyncGenerator[Event]:
        async with contextlib.aclosing(observe_events(self, subject, options)) as generator:
            async for item in generator:
                yield item

    async def register_event_schema(self, event_type: str, json_schema: dict) -> None:
        await register_event_schema(self, event_type, json_schema)

    async def read_subjects(
        self,
        base_subject: str
    ) -> AsyncGenerator[str]:
        async with contextlib.aclosing(read_subjects(self, base_subject)) as generator:
            async for item in generator:
                yield item

    async def read_event_types(self) -> AsyncGenerator[EventType]:
        async with contextlib.aclosing(read_event_types(self)) as generator:
            async for item in generator:
                yield item
