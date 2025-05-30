import aiohttp
import pytest

from .shared.database import Database


class TestPing:
    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_no_error_if_server_is_reachable(database: Database) -> None:
        client = database.get_client("with_authorization")
        await client.ping()

    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_server_is_not_reachable(database: Database) -> None:
        client = database.get_client("with_invalid_url")

        with pytest.raises(aiohttp.ClientError):
            await client.ping()

    @staticmethod
    @pytest.mark.asyncio
    async def test_supports_authorization(database: Database) -> None:
        client = database.get_client()

        await client.ping()
