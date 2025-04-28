import logging
import os
import time
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

    @staticmethod
    def _create_container(api_token, image_tag):
        return Container(
            image_name="thenativeweb/eventsourcingdb",
            image_tag=image_tag,
            api_token=api_token,
            internal_port=3000
        )

    @staticmethod
    async def _initialize_clients(container, api_token):
        with_authorization_client = container.get_client()
        await with_authorization_client.initialize()

        with_authorization = TestingDatabase(
            with_authorization_client,
            container
        )

        with_invalid_url_client = Client(
            base_url='http://localhost.invalid',
            api_token=api_token
        )
        await with_invalid_url_client.initialize()

        with_invalid_url = TestingDatabase(
            with_invalid_url_client
        )
        return with_authorization, with_invalid_url

    @staticmethod
    def _stop_container_safely(container):
        """Safely stop a container, ignoring errors"""
        try:
            container.stop()
        except OSError:
            pass

    @classmethod
    async def create(cls, max_retries=3, retry_delay=2.0) -> 'Database':
        api_token = str(uuid.uuid4())
        image_tag = cls._get_image_tag_from_dockerfile()
        container = cls._create_container(api_token, image_tag)
        error = None

        for attempt in range(max_retries):
            try:
                container.start()
            except OSError as caught_error:
                error = caught_error
                retry = True
            except Exception as unexpected_error:
                cls._stop_container_safely(container)
                raise unexpected_error
            else:
                retry = False

            if retry:
                if attempt == max_retries - 1:
                    cls._stop_container_safely(container)
                    msg = f"Failed to initialize database container after {max_retries} attempts"
                    raise RuntimeError(f"{msg}: {error}") from error
                logging.warning(
                    "Container startup attempt %d failed: %s. Retrying in %s seconds...",
                    attempt + 1, error, retry_delay
                )
                time.sleep(retry_delay)
                cls._stop_container_safely(container)
                container = cls._create_container(api_token, "latest")
                continue

            try:
                auth_db, invalid_url_db = await cls._initialize_clients(container, api_token)
            except Exception as client_error:
                cls._stop_container_safely(container)
                raise client_error

            return cls(Database.__create_key, auth_db, invalid_url_db)

        raise RuntimeError("Failed to create database: Unexpected error during retry loop")

    @staticmethod
    def _get_image_tag_from_dockerfile():
        dockerfile_path = os.path.join(
            os.path.dirname(__file__),
            'docker/eventsourcingdb/Dockerfile')
        with open(dockerfile_path, 'r', encoding='utf-8') as dockerfile:
            content = dockerfile.read().strip()
            return content.split(':')[-1]

    async def stop(self):
        await self.with_authorization.stop()
        await self.with_invalid_url.stop()
