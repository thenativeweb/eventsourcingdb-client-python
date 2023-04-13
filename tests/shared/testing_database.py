from eventsourcingdb_client_python.client import Client
from dataclasses import dataclass


@dataclass
class TestingDatabase:
    client: Client
