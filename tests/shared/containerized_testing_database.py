from eventsourcingdb_client_python.client import Client
from eventsourcingdb_client_python.client_options import ClientOptions

from .docker.container import Container
from .docker.image import Image


class ContainerizedTestingDatabase:
    __create_key = object()

    def __init__(
        self,
        create_key,
        container: Container,
        client: Client
    ):
        assert create_key == ContainerizedTestingDatabase.__create_key, \
            'ContainerizedTestingDatabase objects must be created ' \
            'using ContainerizedTestingDatabase.create.'

        self.__client: Client = client
        self.__container: Container = container

    @classmethod
    async def create(
        cls,
        image: Image,
        command: [str],
        access_token: str,
        options: ClientOptions = ClientOptions(),
    ) -> 'ContainerizedTestingDatabase':
        container = image.run(command, True, True)
        exposed_port = container.get_exposed_port(3_000)
        base_url = f'http://127.0.0.1:{exposed_port}'
        client = await Client.create(base_url, access_token=access_token, options=options)

        await client.ping()

        return cls(
            ContainerizedTestingDatabase.__create_key,
            container,
            client
        )

    async def stop(self) -> None:
        self.__container.kill()
        await self.client.close()

    @property
    def client(self) -> Client:
        return self.__client
