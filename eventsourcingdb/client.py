from collections.abc import AsyncGenerator
from contextlib import aclosing
from types import TracebackType
from typing import Any, Self, TypeAlias, TypeVar

from .errors import CustomError, InternalError
from .event import Event, EventCandidate
from .http_client import DEFAULT_STALL_TIMEOUT_SECONDS, HttpClient
from .observe_events import ObserveEventsOptions
from .read_event_types import EventType
from .read_events import ReadEventsOptions
from .transport import ChooseTransport
from .write_events import Precondition

T = TypeVar('T')

# Type aliases for commonly used types
JsonDict: TypeAlias = dict[str, Any]
EventCandidateList: TypeAlias = list[EventCandidate]
PreconditionList: TypeAlias = list[Precondition]
EventStream: TypeAlias = AsyncGenerator[Event, None]
EventTypeStream: TypeAlias = AsyncGenerator[EventType, None]
SubjectStream: TypeAlias = AsyncGenerator[str, None]


class Client:
    def __init__(
        self,
        base_url: str,
        api_token: str,
        *,
        stall_timeout: float = DEFAULT_STALL_TIMEOUT_SECONDS,
    ) -> None:
        self.__http_client = HttpClient(
            base_url=base_url,
            api_token=api_token,
            stall_timeout=stall_timeout,
        )
        self.__transports = ChooseTransport(self.__http_client)

    async def __aenter__(self) -> Self:
        await self.__http_client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        await self.__http_client.__aexit__(exc_type, exc_val, exc_tb)

    @property
    def http_client(self) -> HttpClient:
        return self.__http_client

    async def ping(self) -> None:
        transport = await self.__transports.get()
        await transport.ping()

    async def verify_api_token(self) -> None:
        transport = await self.__transports.get()
        await transport.verify_api_token()

    async def write_events(
        self,
        event_candidates: EventCandidateList,
        preconditions: PreconditionList | None = None
    ) -> list[Event]:
        if preconditions is None:
            preconditions = []

        transport = await self.__transports.get()
        return await transport.write_events(event_candidates, preconditions)

    async def read_events(
        self,
        subject: str,
        options: ReadEventsOptions
    ) -> EventStream:
        transport = await self.__transports.get()
        async with aclosing(transport.read_events(subject, options)) as events:
            async for event in events:
                yield event

    async def run_eventql_query(self, query: str) -> AsyncGenerator[Any]:
        transport = await self.__transports.get()
        async with aclosing(transport.run_eventql_query(query)) as rows:
            async for row in rows:
                yield row

    async def observe_events(
        self,
        subject: str,
        options: ObserveEventsOptions
    ) -> EventStream:
        transport = await self.__transports.get()
        async with aclosing(transport.observe_events(subject, options)) as events:
            async for event in events:
                yield event

    async def register_event_schema(self, event_type: str, json_schema: JsonDict) -> None:
        transport = await self.__transports.get()
        await transport.register_event_schema(event_type, json_schema)

    async def read_subjects(
        self,
        base_subject: str
    ) -> SubjectStream:
        transport = await self.__transports.get()
        async with aclosing(transport.read_subjects(base_subject)) as subjects:
            async for subject in subjects:
                yield subject

    async def read_event_type(self, event_type: str) -> EventType:
        transport = await self.__transports.get()
        return await transport.read_event_type(event_type)

    async def read_event_types(self) -> EventTypeStream:
        # Reading event types wraps every error of the request that is not one
        # of the client SDK in an InternalError, so choosing the transport,
        # which may send a request of its own, does as well.
        try:
            transport = await self.__transports.get()
        except CustomError:
            raise
        except Exception as error:
            raise InternalError(str(error)) from error

        async with aclosing(transport.read_event_types()) as event_types:
            async for event_type in event_types:
                yield event_type
