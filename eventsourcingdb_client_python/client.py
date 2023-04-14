from collections.abc import Generator

from .abstract_base_client import AbstractBaseClient
from .client_configuration import ClientConfiguration
from .client_options import ClientOptions
from .event.event_candidate import EventCandidate
from .event.event_context import EventContext
from .handlers.read_events.read_events import read_events
from .handlers.read_events.read_events_options import ReadEventsOptions
from .http_client import HttpClient
from .handlers.ping import ping
from .handlers.read_subjects import read_subjects, ReadSubjectsOptions
from .handlers.write_events import Precondition, write_events


class Client(AbstractBaseClient):
    def __init__(
        self,
        base_url: str,
        options: ClientOptions = ClientOptions()
    ):
        self.configuration: ClientConfiguration = ClientConfiguration(
            base_url=base_url,
            timeout_seconds=options.timeout_seconds,
            access_token=options.access_token,
            protocol_version=options.protocol_version,
            max_tries=options.max_tries
        )

        self.__http_client: HttpClient = HttpClient(self.configuration)

    @property
    def http_client(self) -> HttpClient:
        return self.__http_client

    def ping(self) -> None:
        return ping(self)

    def read_subjects(
        self,
        options: ReadSubjectsOptions = ReadSubjectsOptions()
    ) -> Generator[str, None, None]:
        return read_subjects(self, options)

    def read_events(
        self,
        subject: str,
        options: ReadEventsOptions
    ):
        return read_events(self, subject, options)

    def write_events(
        self,
        event_candidates: list[EventCandidate],
        preconditions: list[Precondition] = None
    ) -> list[EventContext]:
        if preconditions is None:
            preconditions = []
        return write_events(self, event_candidates, preconditions)
