import pytest

from eventsourcingdb.client import Client
from eventsourcingdb.errors.custom_error import CustomError
from eventsourcingdb.errors.server_error import ServerError

from .shared.database import Database


class TestVerifyApiToken:
    @staticmethod
    @pytest.mark.asyncio
    async def test_does_not_throw_if_token_is_valid(
        database: Database
    ):
        client = database.get_client()
        await client.verify_api_token()


    @staticmethod
    @pytest.mark.asyncio
    async def test_throws_error_if_token_is_invalid(
        database: Database
    ):
        base_url = database.get_base_url()

        valid_token = database.get_api_token()
        invalid_token = f"{valid_token}-invalid"

        client = Client(base_url=base_url, api_token=invalid_token)

        with pytest.raises(ServerError, match="Failed to verify API token"):
            await client.verify_api_token()
