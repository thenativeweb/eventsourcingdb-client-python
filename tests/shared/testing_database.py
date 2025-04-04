from dataclasses import dataclass

from eventsourcingdb.client import Client


@dataclass
class TestingDatabase:
    client: Client

    async def stop(self) -> None:
        await self.client.close()
