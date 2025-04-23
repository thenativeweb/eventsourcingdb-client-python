import uuid
from eventsourcingdb.client import Client
from eventsourcingdb.container import Container
from .testing_database import TestingDatabase

class Database:
    __create_key = object()

    def __init__(
        self,
        create_key,
        with_authorization: TestingDatabase,
        with_invalid_url: TestingDatabase
    ):
        assert create_key == Database.__create_key, \
            'Database objects must be created using Database.create.'

        self.with_authorization: TestingDatabase = with_authorization
        self.with_invalid_url: TestingDatabase = with_invalid_url

    @classmethod
    async def create(cls) -> 'Database':
        api_token = str(uuid.uuid4())
        
        # Erstellen und Starten des Containers mit der zentralen Container-Klasse
        container = Container(
            api_token=api_token
        )
        container.start()
        
        # Client mit Autorisierung erstellen
        with_authorization_client = container.get_client()
        await with_authorization_client.initialize()
        with_authorization = TestingDatabase(
            with_authorization_client,
            container  # Container an TestingDatabase übergeben für cleanup
        )

        # Client mit ungültiger URL erstellen - api_token statt auth_token verwenden
        with_invalid_url_client = Client(
            base_url='http://localhost.invalid',
            api_token=api_token
        )
        await with_invalid_url_client.initialize()
        with_invalid_url = TestingDatabase(
            with_invalid_url_client
        )

        return cls(Database.__create_key, with_authorization, with_invalid_url)

    async def stop(self):
        await self.with_authorization.stop()
        await self.with_invalid_url.stop()
