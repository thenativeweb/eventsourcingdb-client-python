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
            ['run', '--dev', '--ui', '--access-token', f'{access_token}'],
            ClientOptions(access_token=access_token)
        )

        without_authorization = ContainerizedTestingDatabase(
            image,
            ['run', '--dev', '--ui']
        )

        with_invalid_url = TestingDatabase(Client('http://localhost.invalid'))

        self.with_authorization: ContainerizedTestingDatabase = with_authorization
        self.without_authorization: ContainerizedTestingDatabase = without_authorization
        self.with_invalid_url: TestingDatabase = with_invalid_url

    def stop(self):
        self.with_authorization.stop()
        self.without_authorization.stop()
