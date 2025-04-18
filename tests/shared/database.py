import uuid

from eventsourcingdb.client import Client
from eventsourcingdb.client_options import ClientOptions

from .containerized_testing_database import ContainerizedTestingDatabase
from .docker.image import Image
from .testing_database import TestingDatabase


class Database:
    __create_key = object()

    def __init__(
        self,
        create_key,
        with_authorization: ContainerizedTestingDatabase,
        with_invalid_url: TestingDatabase
    ):
        assert create_key == Database.__create_key, \
            'Database objects must be created using Database.create.'

        self.with_authorization: ContainerizedTestingDatabase = with_authorization
        self.with_invalid_url: TestingDatabase = with_invalid_url

    @classmethod
    async def create(cls) -> 'Database':
        image = Image('eventsourcingdb', 'latest')

        api_token = str(uuid.uuid4())
        with_authorization = await ContainerizedTestingDatabase.create(
            image,
            ['run', '--api-token', f'{api_token}', '--data-directory-temporary'],
            api_token,
            ClientOptions()
        )

        with_invalid_url_client = Client(
            base_url='http://localhost.invalid', api_token=api_token
        )
        await with_invalid_url_client.initialize()
        with_invalid_url = TestingDatabase(
            with_invalid_url_client
        )

        return cls(Database.__create_key, with_authorization, with_invalid_url)

    async def stop(self):
        await self.with_authorization.stop()
        await self.with_invalid_url.stop()
