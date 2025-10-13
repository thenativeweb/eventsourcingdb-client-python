import io
import logging
import tarfile
import time
from http import HTTPStatus

import docker
import requests
from docker import DockerClient, errors
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

from .client import Client


class Container:
    def __init__(
        self,
    ) -> None:
        self._image_name: str = "thenativeweb/eventsourcingdb"
        self._image_tag: str = "latest"
        self._api_token: str = "secret"
        self._internal_port: int = 3000
        self._container = None
        self._docker_client: DockerClient = docker.from_env()
        self._mapped_port: int | None = None
        self._host = "localhost"
        self._signing_key: ed25519.Ed25519PrivateKey | None = None

    def _cleanup_existing_containers(self) -> None:
        try:
            containers = self._docker_client.containers.list(
                filters={"ancestor": f"{self._image_name}:{self._image_tag}"}
            )
        except errors.APIError as e:
            logging.warning("Warning: Error listing existing containers: %s", e)
            return

        for container in containers:
            try:
                container.stop()
            except errors.APIError as e:
                logging.warning("Warning: Error stopping container: %s", e)

            try:
                container.remove()
            except errors.APIError as e:
                logging.warning("Warning: Error removing container: %s", e)

    def _create_container(self) -> None:
        port_bindings = {f"{self._internal_port}/tcp": None}

        command = [
            "run",
            "--api-token",
            self._api_token,
            "--data-directory-temporary",
            "--http-enabled",
            "--https-enabled=false",
        ]

        if self._signing_key is not None:
            target_path = "/etc/esdb/signing-key.pem"
            command.extend(["--signing-key-file", target_path])

        self._container = self._docker_client.containers.run(
            f"{self._image_name}:{self._image_tag}",
            command=command,
            ports=port_bindings,  # type: ignore
            detach=True,
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
            self._container.put_archive('/etc', tar_stream)

    def _extract_port_from_container_info(self, container_info) -> int | None:
        port = None
        valid_mapping = True
        port_mappings = None
        host_port_key = "HostPort"

        try:
            port_mappings = container_info["NetworkSettings"]["Ports"].get(
                f"{self._internal_port}/tcp"
            )
        except KeyError:
            valid_mapping = False

        if valid_mapping and port_mappings and isinstance(port_mappings, list) and port_mappings:
            first_mapping = port_mappings[0]

            if host_port_key in first_mapping:
                port_value = first_mapping[host_port_key]
                port = int(port_value)

        return port

    def _fetch_mapped_port(self) -> None:
        if self._container is None:
            raise RuntimeError("Container failed to start")

        max_retries, retry_delay = 5, 1

        for attempt in range(max_retries):
            if (port := self._try_get_port_from_container()) is not None:
                self._mapped_port = port
                return

            if attempt < max_retries - 1:
                time.sleep(retry_delay)

        self._stop_and_remove_container()
        raise RuntimeError("Failed to determine mapped port")

    def _get_container_info(self) -> dict | None:
        if self._container is None:
            return None
        try:
            if self._container.id is None:
                return None
            return self._docker_client.api.inspect_container(self._container.id)
        except (errors.NotFound, errors.APIError):
            return None

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

        self._pull_or_get_image()
        self._cleanup_existing_containers()
        self._create_container()
        self._fetch_mapped_port()
        self._wait_for_http("/api/v1/ping", timeout=20)

        return self

    def _pull_or_get_image(self) -> None:
        try:
            self._docker_client.images.pull(self._image_name, self._image_tag)
        except errors.APIError as e:
            self._handle_image_pull_error(e)

    def _handle_image_pull_error(self, error) -> None:
        image_name = f"{self._image_name}:{self._image_tag}"
        try:
            self._docker_client.images.get(image_name)
        except errors.ImageNotFound:
            raise RuntimeError(
                f"Could not pull image and no local image available: {error}"
            ) from error

        logging.warning("Warning: Could not pull image: %s. Using locally cached image.", error)

    def stop(self) -> None:
        self._stop_and_remove_container()

    def _stop_and_remove_container(self) -> None:
        if self._container is None:
            return

        try:
            self._container.stop()
        except errors.NotFound as e:
            logging.warning("Warning: Container not found while stopping: %s", e)
        except errors.APIError as e:
            logging.warning("Warning: API error while stopping container: %s", e)

        try:
            self._container.remove()
        except errors.NotFound as e:
            logging.warning("Warning: Container not found while removing: %s", e)
        except errors.APIError as e:
            logging.warning("Warning: API error while removing container: %s", e)

        self._container = None
        self._mapped_port = None

    def _try_get_port_from_container(self) -> int | None:
        if not self._container:
            return None

        if not (container_info := self._get_container_info()):
            return None

        return self._extract_port_from_container_info(container_info)

    def _wait_for_http(self, path: str, timeout: int) -> None:
        base_url = self.get_base_url()
        url = f"{base_url}{path}"
        start_time = time.time()

        max_attempts = int(timeout * 2)
        for _ in range(max_attempts):
            if time.time() - start_time >= timeout:
                break

            if self._check_endpoint_available(url):
                return

            time.sleep(0.5)

        self._stop_and_remove_container()
        raise TimeoutError(f"Service failed to become ready within {timeout} seconds")

    def _check_endpoint_available(self, url: str) -> bool:
        try:
            response = requests.get(url, timeout=2)
        except requests.RequestException:
            return False
        return self._check_response_ok(response)

    # pylint: disable=R6301
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

    def get_signing_key(self) -> ed25519.Ed25519PrivateKey:
        if self._signing_key is None:
            raise RuntimeError("Signing key not set.")
        return self._signing_key

    def get_verification_key(self) -> ed25519.Ed25519PublicKey:
        if self._signing_key is None:
            raise RuntimeError("Signing key not set.")
        return self._signing_key.public_key()
