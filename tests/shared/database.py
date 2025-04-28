import uuid
import time
from eventsourcingdb.client import Client
from eventsourcingdb.container import Container
from .testing_database import TestingDatabase
import os


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

    @classmethod
    async def create(cls, max_retries=3, retry_delay=2.0) -> 'Database':
        """Create a new Database instance with retry mechanism for container startup"""
        api_token = str(uuid.uuid4())

        dockerfile_path = os.path.join(
            os.path.dirname(__file__),
            'docker/eventsourcingdb/Dockerfile')
        with open(dockerfile_path, 'r') as dockerfile:
            content = dockerfile.read().strip()
            image_tag = content.split(':')[-1]

        container = Container(
            image_name="thenativeweb/eventsourcingdb",
            image_tag=image_tag,
            api_token=api_token,
            internal_port=3000
        )

        # Try with retries
        for attempt in range(max_retries):
            try:
                # Start the container with timeout handling
                container.start()

                # Create client with authorization
                with_authorization_client = container.get_client()
                await with_authorization_client.initialize()
                with_authorization = TestingDatabase(
                    with_authorization_client,
                    container  # Pass container to TestingDatabase for cleanup
                )

                # Create client with invalid URL but valid token
                with_invalid_url_client = Client(
                    base_url='http://localhost.invalid',
                    api_token=api_token
                )
                await with_invalid_url_client.initialize()
                with_invalid_url = TestingDatabase(
                    with_invalid_url_client
                )

                return cls(Database.__create_key, with_authorization, with_invalid_url)

            except Exception as e:
                # On the last attempt, raise the error
                if attempt == max_retries - 1:
                    # Cleanup the container if it was created
                    try:
                        container.stop()
                    except BaseException:
                        pass
                    raise RuntimeError(
                        f"Failed to initialize database container after {max_retries} attempts: {e}")

                # Otherwise wait and retry
                print(
                    f"Container startup attempt {
                        attempt +
                        1} failed: {e}. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)

                # Try to clean up the failed container before retrying
                try:
                    container.stop()
                except BaseException:
                    pass

                # Create a new container for the next attempt
                container = Container(
                    image_name="thenativeweb/eventsourcingdb",
                    image_tag="latest",
                    api_token=api_token,
                    internal_port=3000
                )

    async def stop(self):
        await self.with_authorization.stop()
        await self.with_invalid_url.stop()
