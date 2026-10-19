import math
import re
import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import docker
import pytest
import requests
from docker.models.containers import ContainerCollection

from eventsourcingdb import Container
from eventsourcingdb.container import DEFAULT_STARTUP_TIMEOUT_SECONDS, START_LABEL

from .shared.image_tag import get_image_tag

CLEANUP_GUARD_SECONDS = 10
FAKE_PORT = 49153
POLL_GUARD_SECONDS = 2


class CreatedContainers:
    """
    Records every container that Container creates, and lets a test change how
    Docker creates it, so that it does not become reachable, exits, or fails.
    """

    def __init__(self) -> None:
        self.start_ids: list[str] = []
        self.container_ids: list[str] = []
        self.change_command: Callable[[list[str]], list[str]] = lambda command: command
        self.extra_arguments: dict[str, Any] = {}
        self.before_create: Callable[[], None] = lambda: None
        self.after_create: Callable[[], None] = lambda: None

    def find_leftovers(self) -> list[str]:
        docker_client = docker.from_env()
        leftovers = set()

        for start_id in self.start_ids:
            for container in docker_client.api.containers(
                all=True, filters={'label': f'{START_LABEL}={start_id}'}
            ):
                leftovers.add(container['Id'])

        for container_id in self.container_ids:
            try:
                docker_client.api.inspect_container(container_id)
            except docker.errors.NotFound:
                continue
            leftovers.add(container_id)

        return sorted(leftovers)

    def wait_until_created_and_removed(self) -> None:
        # A container that Docker creates only after the start gave up is
        # removed in the background, once Docker returns.
        deadline = time.monotonic() + CLEANUP_GUARD_SECONDS
        while not self.container_ids or self.find_leftovers():
            if time.monotonic() >= deadline:
                break
            time.sleep(0.1)

    def remove_leftovers(self) -> None:
        docker_client = docker.from_env()
        for container_id in self.find_leftovers():
            try:
                docker_client.api.remove_container(container_id, force=True)
            except docker.errors.NotFound:
                continue


@pytest.fixture
def created_containers(monkeypatch: pytest.MonkeyPatch) -> CreatedContainers:
    created = CreatedContainers()
    create = ContainerCollection.create

    def spy(collection: ContainerCollection, image: str, command: list[str], **kwargs: Any) -> Any:
        if (start_id := kwargs.get('labels', {}).get(START_LABEL)) is not None:
            created.start_ids.append(start_id)
        created.before_create()
        container = create(
            collection, image, created.change_command(command), **kwargs, **created.extra_arguments
        )
        created.container_ids.append(container.id)
        created.after_create()
        return container

    monkeypatch.setattr(ContainerCollection, 'create', spy)
    yield created
    created.remove_leftovers()


class FakeContainer:
    """
    Stands in for a running container, whose port Docker publishes only from
    the given poll on.
    """

    def __init__(self, published_from_poll: int) -> None:
        self.attrs: dict[str, Any] = {}
        self.polls = 0
        self.published_from_poll = published_from_poll
        self.status = 'running'

    def reload(self) -> None:
        self.polls += 1
        ports = {}
        if self.polls >= self.published_from_poll:
            ports = {'3000/tcp': [{'HostIp': '0.0.0.0', 'HostPort': str(FAKE_PORT)}]}
        self.attrs = {'NetworkSettings': {'Ports': ports}}


class FakePing:
    """
    Answers the pings with the given statuses in turn, and with the last one
    from then on.
    """

    def __init__(self, statuses: list[int]) -> None:
        self.statuses = statuses
        self.urls: list[str] = []

    def __call__(self, url: str, timeout: float) -> SimpleNamespace:
        self.urls.append(url)
        return SimpleNamespace(status_code=self.statuses[min(len(self.urls), len(self.statuses)) - 1])


def listen_on_another_port(command: list[str]) -> list[str]:
    # The server listens on another port than the one that Docker publishes,
    # so the container runs, but the ping never reaches it.
    index = command.index('--http-port')
    return [*command[:index + 1], str(int(command[index + 1]) + 1), *command[index + 2:]]


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
    async def test_starts_a_single_container_and_removes_it_on_stop(
        created_containers: CreatedContainers,
    ) -> None:
        container = Container().with_image_tag(get_image_tag())
        container.start()

        try:
            # Should not throw.
            await container.get_client().ping()
        finally:
            container.stop()

        assert len(created_containers.container_ids) == 1
        assert created_containers.find_leftovers() == []

    @staticmethod
    @pytest.mark.asyncio
    async def test_leaves_containers_alone_that_it_did_not_start() -> None:
        # A container of the same image and tag, but started by someone else,
        # such as another test run or the developer.
        image_tag = get_image_tag()
        docker_client = docker.from_env()
        docker_client.images.pull('thenativeweb/eventsourcingdb', image_tag)
        other_container = docker_client.containers.run(
            f'thenativeweb/eventsourcingdb:{image_tag}',
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
            container = Container().with_image_tag(image_tag)
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


class TestStartupTimeout:
    @staticmethod
    def test_is_30_seconds_by_default() -> None:
        assert DEFAULT_STARTUP_TIMEOUT_SECONDS == 30
        assert Container()._startup_timeout == DEFAULT_STARTUP_TIMEOUT_SECONDS

    @staticmethod
    @pytest.mark.parametrize(
        'startup_timeout',
        [
            pytest.param(0, id='zero'),
            pytest.param(-1, id='negative'),
            pytest.param(math.inf, id='infinite'),
            pytest.param(-math.inf, id='negative infinite'),
            pytest.param(math.nan, id='not a number'),
        ],
    )
    def test_rejects_a_startup_timeout_that_is_not_a_finite_number_greater_than_zero(
        startup_timeout: float,
    ) -> None:
        with pytest.raises(ValueError, match='The startup timeout must be a finite number'):
            Container().with_startup_timeout(startup_timeout)

    @staticmethod
    def test_reads_the_port_again_on_every_poll(monkeypatch: pytest.MonkeyPatch) -> None:
        ping = FakePing([200])
        monkeypatch.setattr(requests, 'get', ping)
        fake_container = FakeContainer(published_from_poll=3)

        mapped_port = Container()._wait_until_reachable(
            fake_container, time.monotonic() + POLL_GUARD_SECONDS
        )

        assert mapped_port == FAKE_PORT
        assert fake_container.polls == 3
        assert ping.urls == [f'http://localhost:{FAKE_PORT}/api/v1/ping']

    @staticmethod
    def test_accepts_only_status_200_from_the_ping(monkeypatch: pytest.MonkeyPatch) -> None:
        ping = FakePing([204, 500, 200])
        monkeypatch.setattr(requests, 'get', ping)
        fake_container = FakeContainer(published_from_poll=1)

        mapped_port = Container()._wait_until_reachable(
            fake_container, time.monotonic() + POLL_GUARD_SECONDS
        )

        assert mapped_port == FAKE_PORT
        assert len(ping.urls) == 3

    @staticmethod
    def test_replaces_a_running_container_that_does_not_become_reachable_in_time(
        created_containers: CreatedContainers,
    ) -> None:
        created_containers.change_command = listen_on_another_port

        container = Container().with_image_tag(get_image_tag()).with_startup_timeout(1.5)

        started_at = time.monotonic()
        with pytest.raises(TimeoutError) as error:
            container.start()
        elapsed = time.monotonic() - started_at

        assert str(error.value) == (
            'Failed to start the container, the database did not become reachable '
            'within 1.5s in any of 3 containers'
        )
        assert len(created_containers.container_ids) == 3
        assert len(set(created_containers.start_ids)) == 3
        assert elapsed >= 3 * 1.5
        assert created_containers.find_leftovers() == []
        assert not container.is_running()

    @staticmethod
    def test_fails_at_once_with_the_log_tail_if_the_container_exits(
        created_containers: CreatedContainers,
    ) -> None:
        # The container prints 30 lines to a single stream and exits, so that
        # the order of its log is known. EventSourcingDB itself writes to both
        # stdout and stderr, whose lines Docker interleaves in no fixed order.
        created_containers.extra_arguments = {
            'entrypoint': [
                '/bin/sh',
                '-c',
                'for line in $(seq 1 30); do echo "line $line"; done; exit 1',
            ],
        }
        container = Container().with_image_tag(get_image_tag()).with_startup_timeout(5)

        with pytest.raises(RuntimeError) as error:
            container.start()

        log_tail = '\n'.join(f'line {line}' for line in range(11, 31))
        assert str(error.value) == (
            f'Failed to start the container, it exited before the database became reachable: {log_tail}'
        )
        assert len(created_containers.container_ids) == 1
        assert created_containers.find_leftovers() == []

    @staticmethod
    def test_fails_at_once_with_the_error_of_docker_if_the_image_does_not_exist(
        created_containers: CreatedContainers,
    ) -> None:
        container = Container().with_image_tag('this-tag-does-not-exist')

        with pytest.raises(RuntimeError) as error:
            container.start()

        assert isinstance(error.value.__cause__, docker.errors.APIError)
        assert str(error.value) == f'Failed to start the container: {error.value.__cause__}'
        assert created_containers.container_ids == []

    @staticmethod
    def test_fails_at_once_and_removes_the_container_if_docker_fails_to_start_it(
        created_containers: CreatedContainers,
    ) -> None:
        created_containers.extra_arguments = {'entrypoint': ['/this-file-does-not-exist']}
        container = Container().with_image_tag(get_image_tag())

        with pytest.raises(RuntimeError) as error:
            container.start()

        assert isinstance(error.value.__cause__, docker.errors.APIError)
        assert str(error.value) == f'Failed to start the container: {error.value.__cause__}'
        assert len(created_containers.container_ids) == 1
        assert created_containers.find_leftovers() == []

    @staticmethod
    def test_removes_the_container_if_docker_creates_it_but_the_call_fails(
        created_containers: CreatedContainers,
    ) -> None:
        def lose_the_response() -> None:
            raise requests.exceptions.ReadTimeout('Read timed out.')

        created_containers.after_create = lose_the_response
        container = Container().with_image_tag(get_image_tag())

        with pytest.raises(
            RuntimeError, match=re.escape('Failed to start the container: Read timed out.')
        ):
            container.start()

        assert len(created_containers.container_ids) == 1
        assert created_containers.find_leftovers() == []

    @staticmethod
    def test_removes_the_container_if_docker_creates_it_only_after_the_time_is_up(
        created_containers: CreatedContainers,
    ) -> None:
        created_containers.before_create = lambda: time.sleep(2)
        container = Container().with_image_tag(get_image_tag()).with_startup_timeout(1)

        with pytest.raises(
            RuntimeError, match=re.escape('Failed to start the container: Docker did not answer within 1s')
        ):
            container.start()

        # Docker has not even returned yet.
        assert created_containers.container_ids == []

        created_containers.wait_until_created_and_removed()
        assert len(created_containers.container_ids) == 1
        assert created_containers.find_leftovers() == []
