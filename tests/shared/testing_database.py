from dataclasses import dataclass

from eventsourcingdb_client_python.client import Client


@dataclass
class TestingDatabase:
    client: Client
