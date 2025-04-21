from collections.abc import AsyncGenerator

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


# pylint: disable=R6007
# Reason: This class explicitly specifies the return type as None
# for better readability. Even though it is not necessary,
# it makes the return type clear without needing to read any
# documentation or code.
class Client():
    def __init__(
        self,
        base_url: str,
        api_token: str,
    ):
        configuration = ClientConfiguration(
            base_url=base_url,
            api_token=api_token,
        )

        self.__http_client = HttpClient(configuration)

    #TODO: is this necessary? __enter__, __exit__
    async def initialize(self) -> None:
        await self.__http_client.initialize()

     #TODO: is this necessary? magic method __enter__, __exit__
    async def close(self) -> None:
        await self.__http_client.close()

    @property
    def http_client(self) -> HttpClient:
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
        async for event in read_events(self, subject, options):
            yield event

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
        async for event in observe_events(self, subject, options):
            yield event

    async def register_event_schema(self, event_type: str, json_schema: str) -> None: # TODO: no json_schema is dict no string anymore
        # no context manager liek read_events
        await register_event_schema(self, event_type, json_schema)

    async def read_subjects(
        self,
        base_subject: str
    ) -> AsyncGenerator[str, None]:
        # TODO: the same issue like read_events. contextmanager
        async for subject in read_subjects(self, base_subject):
            yield subject

    
    async def read_event_types(self) -> AsyncGenerator[EventType, None]:
        # TODO: the same issue like read_events. contextmanager
        async for event_type in read_event_types(self):
            yield event_type



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