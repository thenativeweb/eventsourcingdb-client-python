import uuid

from eventsourcingdb_client_python.client import Client
from eventsourcingdb_client_python.client_options import ClientOptions

from .containerized_testing_database import ContainerizedTestingDatabase
from .docker.image import Image
from .testing_database import TestingDatabase


class Database:
    def __init__(self):
        image = Image('eventsourcingdb', 'latest')

        access_token = str(uuid.uuid4())
        with_authorization = ContainerizedTestingDatabase(
            image,
            ['run', '--access-token', f'{access_token}', '--store-temporary'],
            access_token,
            ClientOptions()
        )

        with_invalid_url = TestingDatabase(
            Client(base_url='http://localhost.invalid', access_token=access_token)
        )

        self.with_authorization: ContainerizedTestingDatabase = with_authorization
        self.with_invalid_url: TestingDatabase = with_invalid_url

    def stop(self):
        self.with_authorization.stop()
