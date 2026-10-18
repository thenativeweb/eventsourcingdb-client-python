import pytest

from eventsourcingdb import Container

from .shared.image_tag import get_image_tag


class TestContainer:
    @staticmethod
    @pytest.mark.asyncio
    async def test_starts_with_a_custom_port() -> None:
        container = Container().with_image_tag(get_image_tag()).with_port(4000)
        container.start()

        try:
            client = container.get_client()

            # Should not throw.
            await client.ping()
        finally:
            container.stop()
