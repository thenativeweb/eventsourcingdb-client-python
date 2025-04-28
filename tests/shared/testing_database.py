from typing import Optional
from eventsourcingdb.client import Client
from eventsourcingdb.container import Container


class TestingDatabase:
    def __init__(
        self,
        client: Client,
        container: Optional[Container] = None
    ):
        self.__client = client
        self.__container = container

    async def stop(self) -> None:
        if self.__container is not None:
            self.__container.stop()
        await self.client.close()

    @property
    def client(self) -> Client:
        return self.__client
