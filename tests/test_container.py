import pytest

from eventsourcingdb import Container

from .shared.database import Database


class TestContainer:
    @staticmethod
    @pytest.mark.asyncio
    async def test_starts_with_a_custom_port() -> None:
        image_tag = Database._get_image_tag_from_dockerfile()
        container = Container().with_image_tag(image_tag).with_port(4000)
        container.start()

        try:
            client = container.get_client()

            # Should not throw.
            await client.ping()
        finally:
            container.stop()
