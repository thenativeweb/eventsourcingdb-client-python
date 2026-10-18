import docker
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

    @staticmethod
    @pytest.mark.asyncio
    async def test_leaves_containers_alone_that_it_did_not_start() -> None:
        # A container of the same image and tag, but started by someone else,
        # such as another test run or the developer.
        image = 'thenativeweb/eventsourcingdb:latest'
        docker_client = docker.from_env()
        docker_client.images.pull('thenativeweb/eventsourcingdb', 'latest')
        other_container = docker_client.containers.run(
            image,
            command=[
                'run',
                '--api-token',
                'secret',
                '--data-directory-temporary',
                '--http-enabled',
                '--https-enabled=false',
            ],
            detach=True,
        )

        try:
            container = Container().with_image_tag('latest')
            container.start()

            try:
                other_container.reload()
                assert other_container.status == 'running'
            finally:
                container.stop()

            other_container.reload()
            assert other_container.status == 'running'
        finally:
            other_container.remove(force=True)
