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
from docker.models.images import ImageCollection

from eventsourcingdb import Container
from eventsourcingdb.container import (
    DEFAULT_STARTUP_TIMEOUT_SECONDS,
    PING_TIMEOUT_SECONDS,
    START_LABEL,
)

from .shared.image_tag import get_image_tag

CLEANUP_GUARD_SECONDS = 10
DOCKER_GUARD_SECONDS = 60
FAKE_PORT = 49153
POLL_GUARD_SECONDS = 2

V1_PING_URL = f'http://localhost:{FAKE_PORT}/api/v1/ping'
V2_PING_URL = f'http://localhost:{FAKE_PORT}/api/v2/system/ping'


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
    Answers the pings of each URL with the given answers in turn, and with the
    last one from then on. An answer is a status, or an error that the ping
    raises instead, such as when the connection is refused or the ping hits its
    bound. A URL without answers is answered with 404, as a server answers a
    path that it does not know.
    """

    def __init__(self, answers: dict[str, list[int | requests.RequestException]]) -> None:
        self.answers = answers
        self.urls: list[str] = []
        self.timeouts: list[float | None] = []

    def __call__(self, url: str, timeout: float | None = None) -> SimpleNamespace:
        self.urls.append(url)
        self.timeouts.append(timeout)

        # As requests does, which refuses a bound that leaves no time at all.
        if timeout is not None and timeout <= 0:
            raise ValueError(f'The ping must have time left, but its bound is {timeout}.')

        answers = self.answers.get(url, [404])
        answer = answers[min(self.urls.count(url), len(answers)) - 1]
        if isinstance(answer, requests.RequestException):
            raise answer
        return SimpleNamespace(status_code=answer)


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


class TestWaitingForTheDatabase:
    """
    Every attempt asks the ping of the v2 API, and the ping of the v1 API only
    if the server answers that with 404 or 405, as a server without the v2 API
    does, so that the container becomes ready against servers with either API.
    """

    @staticmethod
    def test_is_ready_once_the_v2_api_answers_its_ping_without_asking_the_v1_api(
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ping = FakePing({V2_PING_URL: [200], V1_PING_URL: [200]})
        monkeypatch.setattr(requests, 'get', ping)

        mapped_port = Container()._wait_until_reachable(
            FakeContainer(published_from_poll=1), time.monotonic() + POLL_GUARD_SECONDS
        )

        assert mapped_port == FAKE_PORT
        assert ping.urls == [V2_PING_URL]

    @staticmethod
    def test_is_ready_once_the_v2_api_answers_its_ping_if_the_server_lacks_the_v1_api(
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ping = FakePing({V2_PING_URL: [200], V1_PING_URL: [404]})
        monkeypatch.setattr(requests, 'get', ping)

        mapped_port = Container()._wait_until_reachable(
            FakeContainer(published_from_poll=1), time.monotonic() + POLL_GUARD_SECONDS
        )

        assert mapped_port == FAKE_PORT
        assert ping.urls == [V2_PING_URL]

    @staticmethod
    @pytest.mark.parametrize('status', [404, 405])
    def test_asks_the_v1_api_within_the_same_attempt_if_the_server_lacks_the_v2_api(
        status: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ping = FakePing({V2_PING_URL: [status], V1_PING_URL: [200]})
        monkeypatch.setattr(requests, 'get', ping)
        fake_container = FakeContainer(published_from_poll=1)

        mapped_port = Container()._wait_until_reachable(
            fake_container, time.monotonic() + POLL_GUARD_SECONDS
        )

        assert mapped_port == FAKE_PORT
        assert ping.urls == [V2_PING_URL, V1_PING_URL]
        assert fake_container.polls == 1
        assert all(
            timeout is not None and 0 < timeout <= PING_TIMEOUT_SECONDS
            for timeout in ping.timeouts
        ), f'Every ping must be bounded, but the bounds were {ping.timeouts}.'

    @staticmethod
    @pytest.mark.parametrize(
        'failure',
        [
            pytest.param(503, id='another status'),
            pytest.param(requests.exceptions.ReadTimeout('Read timed out.'), id='bound per request'),
            pytest.param(requests.exceptions.ConnectionError('Connection refused.'), id='refused'),
        ],
    )
    def test_tries_again_without_asking_the_v1_api_if_the_ping_of_the_v2_api_fails_otherwise(
        failure: int | requests.RequestException, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ping = FakePing({V2_PING_URL: [failure, 200], V1_PING_URL: [200]})
        monkeypatch.setattr(requests, 'get', ping)
        fake_container = FakeContainer(published_from_poll=1)

        mapped_port = Container()._wait_until_reachable(
            fake_container, time.monotonic() + POLL_GUARD_SECONDS
        )

        assert mapped_port == FAKE_PORT
        assert ping.urls == [V2_PING_URL, V2_PING_URL]
        assert fake_container.polls == 2

    @staticmethod
    @pytest.mark.parametrize(
        'failure',
        [
            pytest.param(503, id='another status'),
            pytest.param(requests.exceptions.ReadTimeout('Read timed out.'), id='bound per request'),
        ],
    )
    def test_starts_the_next_attempt_with_the_v2_api_if_the_ping_of_the_v1_api_fails(
        failure: int | requests.RequestException, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ping = FakePing({V2_PING_URL: [404, 200], V1_PING_URL: [failure]})
        monkeypatch.setattr(requests, 'get', ping)
        fake_container = FakeContainer(published_from_poll=1)

        mapped_port = Container()._wait_until_reachable(
            fake_container, time.monotonic() + POLL_GUARD_SECONDS
        )

        assert mapped_port == FAKE_PORT
        assert ping.urls == [V2_PING_URL, V1_PING_URL, V2_PING_URL]
        assert fake_container.polls == 2

    @staticmethod
    def test_does_not_ask_the_v1_api_once_the_ping_of_the_v2_api_used_up_the_time(
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ping = FakePing({V2_PING_URL: [404], V1_PING_URL: [200]})
        deadline = time.monotonic() + 0.5

        def answer_once_the_time_is_up(url: str, timeout: float | None = None) -> SimpleNamespace:
            time.sleep(max(deadline - time.monotonic(), 0))
            return ping(url, timeout)

        monkeypatch.setattr(requests, 'get', answer_once_the_time_is_up)

        mapped_port = Container()._wait_until_reachable(FakeContainer(published_from_poll=1), deadline)

        assert mapped_port is None
        assert ping.urls == [V2_PING_URL]


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
        ping = FakePing({V2_PING_URL: [200]})
        monkeypatch.setattr(requests, 'get', ping)
        fake_container = FakeContainer(published_from_poll=3)

        mapped_port = Container()._wait_until_reachable(
            fake_container, time.monotonic() + POLL_GUARD_SECONDS
        )

        assert mapped_port == FAKE_PORT
        assert fake_container.polls == 3
        assert ping.urls == [V2_PING_URL]

    @staticmethod
    def test_accepts_only_status_200_from_the_ping(monkeypatch: pytest.MonkeyPatch) -> None:
        ping = FakePing({V2_PING_URL: [204, 500, 200]})
        monkeypatch.setattr(requests, 'get', ping)
        fake_container = FakeContainer(published_from_poll=1)

        mapped_port = Container()._wait_until_reachable(
            fake_container, time.monotonic() + POLL_GUARD_SECONDS
        )

        assert mapped_port == FAKE_PORT
        assert ping.urls == [V2_PING_URL] * 3

    @staticmethod
    def test_replaces_a_running_container_that_does_not_become_reachable_in_time(
        created_containers: CreatedContainers, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        created_containers.change_command = listen_on_another_port

        # Docker may take as long as it needs to create and start a container,
        # so that the time runs out while waiting for the database, however
        # busy Docker is, and not while Docker has not answered yet.
        create_and_start_container = Container._create_and_start_container

        def without_a_deadline_for_docker(
            container: Container, docker_client: Any, start_id: str, _: float
        ) -> Any:
            return create_and_start_container(
                container, docker_client, start_id, time.monotonic() + DOCKER_GUARD_SECONDS
            )

        monkeypatch.setattr(
            Container, '_create_and_start_container', without_a_deadline_for_docker
        )
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
    def test_fails_at_once_with_the_error_of_docker_if_docker_rejects_the_image(
        created_containers: CreatedContainers,
    ) -> None:
        # Docker rejects the reference on its own, without asking a registry.
        container = Container().with_image_tag('not a valid tag')

        with pytest.raises(RuntimeError) as error:
            container.start()

        assert isinstance(error.value.__cause__, docker.errors.APIError)
        assert error.value.__cause__.status_code == 400
        assert str(error.value) == f'Failed to start the container: {error.value.__cause__}'
        assert created_containers.container_ids == []

    @staticmethod
    def test_fails_at_once_with_the_error_of_the_pull_if_the_image_is_neither_in_the_registry_nor_local(
        created_containers: CreatedContainers, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The registry's answer is made up, so that the test does not depend
        # on the registry or the network. Docker looks for the image locally.
        pull_error = docker.errors.NotFound('manifest unknown')

        def pull(*_: Any, **__: Any) -> None:
            raise pull_error

        monkeypatch.setattr(ImageCollection, 'pull', pull)
        container = Container().with_image_tag('this-tag-does-not-exist')

        with pytest.raises(RuntimeError) as error:
            container.start()

        assert error.value.__cause__ is pull_error
        assert str(error.value) == f'Failed to start the container: {pull_error}'
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
