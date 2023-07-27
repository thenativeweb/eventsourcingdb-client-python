from collections.abc import AsyncGenerator

from .abstract_base_client import AbstractBaseClient
from .client_configuration import ClientConfiguration
from .client_options import ClientOptions
from .event.event_candidate import EventCandidate
from .event.event_context import EventContext
from .handlers.observe_events.observe_events import observe_events
from .handlers.observe_events.observe_events_options import ObserveEventsOptions
from .http_client.http_client import HttpClient
from .handlers.ping import ping
from .handlers.read_events import read_events, ReadEventsOptions
from .handlers.read_subjects import read_subjects
from .handlers.store_item import StoreItem
from .handlers.write_events import Precondition, write_events


class Client(AbstractBaseClient):
    def __init__(
        self,
        base_url: str,
        access_token: str,
        options: ClientOptions = ClientOptions(),
    ):
        configuration = ClientConfiguration(
            base_url=base_url,
            timeout_seconds=options.timeout_seconds,
            access_token=access_token,
            protocol_version=options.protocol_version,
            max_tries=options.max_tries
        )

        self.__http_client = HttpClient(configuration)

    @property
    def http_client(self) -> HttpClient:
        return self.__http_client

    async def ping(self) -> None:
        return await ping(self)

    async def read_subjects(
        self,
        base_subject: str
    ) -> AsyncGenerator[str, None]:
        async for subject in read_subjects(self, base_subject):
            yield subject

    async def read_events(
        self,
        subject: str,
        options: ReadEventsOptions
    ) -> AsyncGenerator[StoreItem, None]:
        async for event in read_events(self, subject, options):
            yield event

    async def observe_events(
        self,
        subject: str,
        options: ObserveEventsOptions
    ) -> AsyncGenerator[StoreItem, None]:
        events = observe_events(self, subject, options)
        async for event in events:
            yield event
        print("calling close")
        await events.aclose()


    async def write_events(
        self,
        event_candidates: list[EventCandidate],
        preconditions: list[Precondition] = None
    ) -> AsyncGenerator[EventContext, None]:
        if preconditions is None:
            preconditions = []
        async for context in write_events(self, event_candidates, preconditions):
            yield context
