import asyncio
import logging
import uuid
from types import TracebackType
from typing import Self

import aiohttp

from eventsourcingdb.client import Client
from eventsourcingdb.container import Container

from .image_tag import get_image_tag

logger = logging.getLogger(__name__)


class Database:
    __create_key = object()
    __container: Container

    CLIENT_TYPE_WITH_AUTH = 'with_authorization'
    CLIENT_TYPE_INVALID_URL = 'with_invalid_url'

    def __init__(
        self,
        create_key,
        with_authorization_client: Client,
        with_invalid_url_client: Client,
    ) -> None:
        assert create_key == Database.__create_key, \
            'Database objects must be created using Database.create.'
        self.__with_authorization_client: Client = with_authorization_client
        self.__with_invalid_url_client: Client = with_invalid_url_client

    @classmethod
    def _create_container(cls, api_token, image_tag) -> Container:
        cls.__container = Container()
        cls.__container.with_image_tag(image_tag)
        cls.__container.with_api_token(api_token)
        return cls.__container

    @staticmethod
    async def _initialize_clients(container, api_token) -> tuple[Client, Client]:
        with_authorization_client = container.get_client()
        with_invalid_url_client = Client(
            base_url='http://localhost.invalid',
            api_token=api_token
        )
        return with_authorization_client, with_invalid_url_client

    @classmethod
    async def create(cls, max_retries=3, retry_delay=2.0) -> 'Database':
        api_token = str(uuid.uuid4())
        image_tag = get_image_tag()
        container = cls._create_container(api_token, image_tag)
        error = None

        for attempt in range(max_retries):
            try:
                container.start()
            except OSError as caught_error:
                error = caught_error
                retry = True
            except Exception:
                container.stop()
                raise
            else:
                retry = False

            if retry:
                if attempt == max_retries - 1:
                    container.stop()
                    msg = f'Failed to initialize database container after {max_retries} attempts'
                    raise RuntimeError(f'{msg}: {error}') from error
                logger.warning(
                    'Container startup attempt %d failed: %s. Retrying in %s seconds...',
                    attempt + 1, error, retry_delay
                )
                await asyncio.sleep(retry_delay)
                container.stop()
                container = cls._create_container(api_token, image_tag)
                continue

            try:
                (
                    with_authorization_client,
                    with_invalid_url_client
                ) = await cls._initialize_clients(
                    container,
                    api_token
                )
            except Exception:
                container.stop()
                raise

            return cls(Database.__create_key, with_authorization_client, with_invalid_url_client)

        raise RuntimeError('Failed to create database: Unexpected error during retry loop')

    def get_client(self, client_type: str = CLIENT_TYPE_WITH_AUTH) -> Client:
        if client_type == self.CLIENT_TYPE_WITH_AUTH:
            return self.__with_authorization_client
        if client_type == self.CLIENT_TYPE_INVALID_URL:
            return self.__with_invalid_url_client

        raise ValueError(f'Unknown client type: {client_type}')

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None
    ) -> None:
        await self.stop()

    def get_base_url(self) -> str:
        return self.__container.get_base_url()

    def get_api_token(self) -> str:
        return self.__container.get_api_token()

    async def offers_v2_api(self) -> bool:
        """
        Tells whether the server offers the v2 API, found out without the
        client SDK, so that tests can expect what each API reports.
        """
        async with (
            aiohttp.ClientSession() as session,
            session.get(f'{self.get_base_url()}/api/v2/system/ping') as response,
        ):
            return response.status == 200

    async def stop(self) -> None:
        if self.__with_authorization_client:
            try:
                await self.__with_authorization_client.__aexit__(None, None, None)
            except (ConnectionError) as e:
                logger.warning("Error closing authorization client: %s", e)

        if self.__with_invalid_url_client:
            try:
                await self.__with_invalid_url_client.__aexit__(None, None, None)
            except (ConnectionError) as e:
                logger.warning("Error closing invalid URL client: %s", e)

        # Then stop the container
        if (container := getattr(self.__class__, '_Database__container', None)):
            container.stop()