import io
import logging
import math
import tarfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from http import HTTPStatus
from typing import ClassVar

import docker
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from docker import DockerClient, errors
from docker.models.containers import Container as DockerContainer

from .client import Client

logger = logging.getLogger(__name__)

DEFAULT_STARTUP_TIMEOUT_SECONDS = 30
START_ATTEMPTS = 3

# Every attempt to start a container labels it with an id of its own, so that a
# failed attempt finds its container even if Docker never handed it over, for
# example because creating it was still pending when the time was up.
START_LABEL = "io.eventsourcingdb.container-start"

# Errors of Docker itself, such as a missing image, a daemon that is not
# running, an invalid configuration, or a call that does not return in time.
# Another container would fail the same way, so they end the start at once.
DOCKER_ERRORS = (errors.DockerException, requests.RequestException, TimeoutError)

LOG_TAIL_LINES = 20
PING_TIMEOUT_SECONDS = 1
POLL_INTERVAL_SECONDS = 0.1


def _format_seconds(seconds: float) -> str:
    # Whole seconds without a fraction, others as short as possible, such as 1.5.
    if float(seconds).is_integer():
        return str(int(seconds))
    return repr(float(seconds))


class Container:
    # Images already pulled in this process. Every container start would
    # otherwise hit the registry again, even though the image is local.
    _pulled_images: ClassVar[set[str]] = set()

    def __init__(
        self,
    ) -> None:
        self._image_name: str = "thenativeweb/eventsourcingdb"
        self._image_tag: str = "latest"
        self._api_token: str = "secret"
        self._internal_port: int = 3000
        self._container: DockerContainer | None = None
        self._docker_client: DockerClient | None = None
        self._mapped_port: int | None = None
        self._host = "localhost"
        self._signing_key: ed25519.Ed25519PrivateKey | None = None
        self._startup_timeout: float = DEFAULT_STARTUP_TIMEOUT_SECONDS

    def _create_container(self, docker_client: DockerClient, start_id: str) -> DockerContainer:
        port_bindings = {f"{self._internal_port}/tcp": None}

        command = [
            "run",
            "--api-token",
            self._api_token,
            "--data-directory-temporary",
            "--http-enabled",
            "--https-enabled=false",
            "--http-port",
            str(self._internal_port),
        ]

        if self._signing_key is not None:
            target_path = "/etc/esdb/signing-key.pem"
            command.extend(["--signing-key-file", target_path])

        # Only create the container for now, so that the signing key can be copied
        # into it before the server starts and tries to read it.
        container = docker_client.containers.create(
            f"{self._image_name}:{self._image_tag}",
            command=command,
            labels={START_LABEL: start_id},
            ports=port_bindings,  # type: ignore
        )  # type: ignore

        # Copy signing key into container if needed
        if self._signing_key is not None:
            signing_key_bytes = self._signing_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )

            # Create tar archive with both the directory structure and the key file
            tar_stream = io.BytesIO()
            tar = tarfile.TarFile(fileobj=tar_stream, mode='w')

            # Add directory entry
            dir_info = tarfile.TarInfo(name='esdb')
            dir_info.type = tarfile.DIRTYPE
            dir_info.mode = 0o755
            tar.addfile(dir_info)

            # Add the key file
            file_info = tarfile.TarInfo(name='esdb/signing-key.pem')
            file_info.size = len(signing_key_bytes)
            file_info.mode = 0o644
            tar.addfile(file_info, io.BytesIO(signing_key_bytes))

            tar.close()
            tar_stream.seek(0)

            # Put the archive into /etc which should exist
            container.put_archive('/etc', tar_stream)

        container.start()

        return container

    def _create_and_start_container(
        self, docker_client: DockerClient, start_id: str, deadline: float
    ) -> DockerContainer:
        # Docker may not return from creating or starting the container in
        # time. Waiting for it in another thread allows to give up once the
        # time is up, and to remove the container once Docker has created it
        # after all.
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._create_container, docker_client, start_id)
        executor.shutdown(wait=False)

        def remove_once_returned(_) -> None:
            self._remove_containers_of_start(docker_client, start_id)

        try:
            done, _ = wait([future], timeout=max(deadline - time.monotonic(), 0))
        except BaseException:
            future.add_done_callback(remove_once_returned)
            raise

        if not done:
            future.add_done_callback(remove_once_returned)
            raise TimeoutError(
                f"Docker did not answer within {_format_seconds(self._startup_timeout)}s"
            )

        return future.result()

    def _extract_port_from_container_info(self, container_info) -> int | None:
        port = None
        valid_mapping = True
        port_mappings = None
        host_port_key = "HostPort"

        try:
            port_mappings = container_info["NetworkSettings"]["Ports"].get(
                f"{self._internal_port}/tcp"
            )
        except (KeyError, AttributeError):
            valid_mapping = False

        if valid_mapping and port_mappings and isinstance(port_mappings, list) and port_mappings:
            first_mapping = port_mappings[0]

            if port_value := first_mapping.get(host_port_key):
                port = int(port_value)

        return port

    def _get_docker_client(self) -> DockerClient:
        if self._docker_client is None:
            self._docker_client = docker.from_env()
        return self._docker_client

    def get_api_token(self) -> str:
        return self._api_token

    def get_base_url(self) -> str:
        if self._container is None:
            raise RuntimeError("Container must be running.")
        return f"http://{self.get_host()}:{self.get_mapped_port()}"

    def get_client(self) -> Client:
        return Client(self.get_base_url(), self.get_api_token())

    def get_host(self) -> str:
        if self._container is None:
            raise RuntimeError("Container must be running.")
        return self._host

    def get_mapped_port(self) -> int:
        if self._container is None or self._mapped_port is None:
            raise RuntimeError("Container must be running.")
        return self._mapped_port

    def is_running(self) -> bool:
        return self._container is not None

    def start(self) -> "Container":
        if self._container is not None:
            return self

        # Pulling the image does not count towards the startup timeout, since
        # it may take long, for example on the first run.
        try:
            docker_client = self._get_docker_client()
            self._pull_or_get_image(docker_client)
        except DOCKER_ERRORS as error:
            raise RuntimeError(f"Failed to start the container: {error}") from error

        # A container that is running but does not become reachable in time is
        # replaced, since Docker sometimes does not publish its port.
        for _ in range(START_ATTEMPTS):
            if self._try_to_start(docker_client):
                return self

        raise TimeoutError(
            "Failed to start the container, the database did not become reachable within "
            f"{_format_seconds(self._startup_timeout)}s in any of {START_ATTEMPTS} containers"
        )

    def _try_to_start(self, docker_client: DockerClient) -> bool:
        start_id = uuid.uuid4().hex
        deadline = time.monotonic() + self._startup_timeout

        try:
            container = self._create_and_start_container(docker_client, start_id, deadline)
            mapped_port = self._wait_until_reachable(container, deadline)
        except DOCKER_ERRORS as error:
            self._remove_containers_of_start(docker_client, start_id)
            raise RuntimeError(f"Failed to start the container: {error}") from error
        except BaseException:
            self._remove_containers_of_start(docker_client, start_id)
            raise

        if mapped_port is None:
            self._remove_containers_of_start(docker_client, start_id)
            return False

        self._container = container
        self._mapped_port = mapped_port
        return True

    def _pull_or_get_image(self, docker_client: DockerClient) -> None:
        image = f"{self._image_name}:{self._image_tag}"

        if image in Container._pulled_images:
            return

        try:
            docker_client.images.pull(self._image_name, self._image_tag)
        except DOCKER_ERRORS as error:
            if not self._has_local_image(docker_client, image):
                raise
            logger.warning("Warning: Could not pull image: %s. Using locally cached image.", error)

        Container._pulled_images.add(image)

    def _has_local_image(self, docker_client: DockerClient, image: str) -> bool:
        try:
            docker_client.images.get(image)
        except errors.ImageNotFound:
            return False
        return True

    def stop(self) -> None:
        self._stop_and_remove_container()

    def _remove_containers_of_start(self, docker_client: DockerClient, start_id: str) -> None:
        try:
            containers = docker_client.api.containers(
                all=True, filters={"label": f"{START_LABEL}={start_id}"}
            )
        except DOCKER_ERRORS as e:
            logger.warning("Warning: Could not list the containers of a failed start: %s", e)
            return

        for container in containers:
            try:
                docker_client.api.remove_container(container["Id"], force=True)
            except errors.NotFound:
                continue
            except DOCKER_ERRORS as e:
                logger.warning("Warning: Could not remove the container of a failed start: %s", e)

    def _stop_and_remove_container(self) -> None:
        if self._container is None:
            return

        try:
            self._container.stop()
        except errors.NotFound as e:
            logger.warning("Warning: Container not found while stopping: %s", e)
        except errors.APIError as e:
            logger.warning("Warning: API error while stopping container: %s", e)

        try:
            self._container.remove()
        except errors.NotFound as e:
            logger.warning("Warning: Container not found while removing: %s", e)
        except errors.APIError as e:
            logger.warning("Warning: API error while removing container: %s", e)

        self._container = None
        self._mapped_port = None

    def _wait_until_reachable(self, container: DockerContainer, deadline: float) -> int | None:
        while True:
            # Docker sometimes publishes the port late, so it is read again on
            # every poll.
            container.reload()

            if container.status in ("exited", "dead"):
                log_tail = container.logs(tail=LOG_TAIL_LINES).decode("utf-8", errors="replace")
                raise RuntimeError(
                    "Failed to start the container, it exited before the database became "
                    f"reachable: {log_tail.rstrip()}"
                )

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None

            mapped_port = self._extract_port_from_container_info(container.attrs)
            if mapped_port is not None and self._check_endpoint_available(
                f"http://{self._host}:{mapped_port}/api/v1/ping",
                min(remaining, PING_TIMEOUT_SECONDS),
            ):
                return mapped_port

            time.sleep(max(min(POLL_INTERVAL_SECONDS, deadline - time.monotonic()), 0))

    def _check_endpoint_available(self, url: str, timeout: float) -> bool:
        try:
            response = requests.get(url, timeout=timeout)
        except requests.RequestException:
            return False
        return self._check_response_ok(response)

    def _check_response_ok(self, response: requests.Response) -> bool:
        return response is not None and response.status_code == HTTPStatus.OK

    def with_api_token(self, token: str) -> "Container":
        self._api_token = token
        return self

    def with_image_tag(self, tag: str) -> "Container":
        self._image_tag = tag
        return self

    def with_port(self, port: int) -> "Container":
        self._internal_port = port
        return self

    def with_signing_key(self) -> "Container":
        self._signing_key = ed25519.Ed25519PrivateKey.generate()
        return self

    def with_startup_timeout(self, timeout: float) -> "Container":
        # There is no way to turn the startup timeout off, since starting would
        # then wait forever for a container that does not become reachable.
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError(
                'The startup timeout must be a finite number of seconds greater than zero, '
                f'but is {timeout}.'
            )

        self._startup_timeout = timeout
        return self

    def get_signing_key(self) -> ed25519.Ed25519PrivateKey:
        if self._signing_key is None:
            raise RuntimeError("Signing key not set.")
        return self._signing_key

    def get_verification_key(self) -> ed25519.Ed25519PublicKey:
        if self._signing_key is None:
            raise RuntimeError("Signing key not set.")
        return self._signing_key.public_key()
