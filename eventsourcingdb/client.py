from collections.abc import AsyncGenerator
from types import TracebackType
from typing import Optional, Type, TypeVar, AsyncIterator

from .client_configuration import ClientConfiguration
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
from .handlers.store_item import StoreItem
from .handlers.write_events import Precondition, write_events


T = TypeVar('T')

class Client:
    def __init__(
        self,
        base_url: str,
        api_token: str,
    ):
        self.__http_client = HttpClient(base_url=base_url, api_token=api_token)

    async def __aenter__(self):
        await self.__http_client.initialize()
        return self

    async def __aexit__(
        self, 
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType]
    ) -> None:
        await self.__http_client.close()

    # Keeping these for backward compatibility and explicit resource management
    """async def initialize(self) -> None:
        await self.__http_client.initialize()

    async def close(self) -> None:
        await self.__http_client.close() # TODO: should we mix object orientation and functional programming?
    """
    def http_client(self) -> # TODO: should we mix object orientation and functional programming?tpClient:
        return self.__http_client

    # TODO: should we mix object orientation and functional programming?
    async def ping(self) -> None:
        return await ping(client=self)
    
    async def verify_api_token(self) -> None:
        ...
    
    async def write_events(
        self,
        event_candidates: list[EventCandidate],
        preconditions: list[Precondition] = None
    ) -> list[EventContext]: # TODO: list[Event] of Events (complete)
        if preconditions is None:
            preconditions = []
        return await write_events(self, event_candidates, preconditions)
    
    async def read_events(
        self,
        subject: str,
        options: ReadEventsOptions
    ) -> AsyncGenerator[StoreItem, None]: # no StoreItem ... it is a Event
        #TODO: This is a code snippet for abort read events.
        """
        https://github.com/thenativeweb/eventsourcingdb-client-javascript/blob/main/src/Client.ts#L134-L152
        for await (const event of client.readEvents('/', { recursive: true })) {
            console.log(event);
            
            if (event.ID === '100') {
                break;
            }
        }


        function handlePostRequest(abortController) {
            const signal = abortController.signal;

            for await (const event of client.readEvents('/', { recursive: true }), signal) {
                console.log(event);
            }
            
            return http.status(200);
        }
"""
        """Read events with proper cancellation support."""
        generator = read_events(self, subject, options)
        try:
            async for item in generator:
                yield item
        finally:
            await generator.aclose()
    # TODO: run eventql query
    async def run_eventql_query(self, query: str) -> AsyncGenerator[Event, None]:
        """
        the issue like read_events. can be abort or canceled.
        """

    async def observe_events(
        self,
        subject: str,
        options: ObserveEventsOptions
    ) -> AsyncGenerator[StoreItem, None]: # no StoreItem ... it is a Event
        """
        TODO: the same issue like read_events. contextmanager
        """
    async def observe_events(
        self,
        subject: str,
        options: ObserveEventsOptions
    ) -> AsyncGenerator[StoreItem, None]:
        generator = observe_events(self, subject, options)
        try:
            async for item in generator:
                yield item
        finally:
            await generator.aclose()

    async def register_event_schema(self, event_type: str, json_schema: dict) -> None:
        # Updated type hint to reflect it should be a dict
        await register_event_schema(self, event_type, json_schema)

    async def read_subjects(
        self,
        base_subject: str
    ) -> AsyncGenerator[str, None]:
        """Read subjects with proper cancellation support."""
        generator = read_subjects(self, base_subject)
        try:
            async for item in generator:
                yield item
        finally:
            await generator.aclose()
    
    async def read_event_types(self) -> AsyncGenerator[EventType, None]:
        """Read event types with proper cancellation support."""
        generator = read_event_types(self)
        try:
            async for item in generator:
                yield item
        finally:
            await generator.aclose()



""" TODO: 

f (response.status !== 200) {
					throw new Error(
						`Failed to read event types, got HTTP status code '${response.status}', expected '200'.`,
					);
				}

"""

"""

A: Ausdüngen und Exception

B: Contextmanager

C: Neue Methoden

D: Testcontainer: testcontainers.com Python "virtuelle Container für tests"
- EventSourcingDB(DockerContainer):
   def __init__(self):
    https://github.com/thenativeweb/eventsourcingdb-client-javascript/blob/main/src/EventSourcingDbContainer.ts
"""

Dokumentationslink für Featurecheck: https://docs.eventsourcingdb.io/client-sdks/compliance-criteria/#detailed-requirements