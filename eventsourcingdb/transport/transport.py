from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any, ClassVar

from ..event import Event, EventCandidate
from ..observe_events import ObserveEventsOptions
from ..read_event_types import EventType
from ..read_events import ReadEventsOptions
from ..write_events import Precondition


class Transport(ABC):
    """
    Speaks one version of the HTTP API of EventSourcingDB. The client chooses
    the transport per server, so that every call works against every server,
    whichever version of the API it offers.
    """

    # The version of the API that the transport speaks, such as v2.
    api_version: ClassVar[str]

    @abstractmethod
    async def ping(self) -> None: ...

    @abstractmethod
    async def verify_api_token(self) -> None: ...

    @abstractmethod
    async def write_events(
        self,
        event_candidates: list[EventCandidate],
        preconditions: list[Precondition],
    ) -> list[Event]: ...

    @abstractmethod
    def read_events(
        self,
        subject: str,
        options: ReadEventsOptions,
    ) -> AsyncGenerator[Event]: ...

    @abstractmethod
    def run_eventql_query(self, query: str) -> AsyncGenerator[Any]: ...

    @abstractmethod
    def observe_events(
        self,
        subject: str,
        options: ObserveEventsOptions,
    ) -> AsyncGenerator[Event]: ...

    @abstractmethod
    async def register_event_schema(self, event_type: str, json_schema: dict[str, Any]) -> None: ...

    @abstractmethod
    def read_subjects(self, subject: str, recursive: bool) -> AsyncGenerator[str]: ...

    @abstractmethod
    async def read_event_type(self, event_type: str) -> EventType: ...

    @abstractmethod
    def read_event_types(self) -> AsyncGenerator[EventType]: ...
