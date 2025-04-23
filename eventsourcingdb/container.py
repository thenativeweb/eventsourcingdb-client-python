import time
import docker
import requests
from typing import Optional
from docker import errors

from eventsourcingdb.client import Client


class Container:
    def __init__(
        self,
        image_name: str = "thenativeweb/eventsourcingdb",
        image_tag: str = "0.113.2",
        api_token: str = "secret",
        internal_port: int = 3000
    ):
        self._image_name = image_name
        self._image_tag = image_tag
        self._internal_port = internal_port
        self._api_token = api_token
        self._container = None
        self._docker_client = docker.from_env()
        self._mapped_port: Optional[int] = None
        self._host = "localhost"

    def with_image_tag(self, tag: str) -> "Container":
        self._image_tag = tag
        return self

    def with_api_token(self, token: str) -> "Container":
        self._api_token = token
        return self

    def with_port(self, port: int) -> "Container":
        self._internal_port = port
        return self

    def start(self) -> "Container":
        if self._container is not None:
            return self
            
        try:
            self._docker_client.images.pull(self._image_name, self._image_tag)
        except errors.APIError as e:
            print(f"Warning: Could not pull image: {e}")

        self._cleanup_existing_containers()
        self._create_container()
        self._fetch_mapped_port()
        self._wait_for_http("/api/v1/ping", timeout=20)
            
        return self

    def _cleanup_existing_containers(self) -> None:
        try:
            for container in self._docker_client.containers.list(
                filters={"ancestor": f"{self._image_name}:{self._image_tag}"}):
                container.stop()
                container.remove()
        except Exception as e:
            print(f"Warning: Error stopping existing containers: {e}")

    def _create_container(self) -> None:
        port_bindings = {f"{self._internal_port}/tcp": None}
        self._container = self._docker_client.containers.run(
            f"{self._image_name}:{self._image_tag}",
            command=[
                "run",
                "--api-token",
                self._api_token,
                "--data-directory-temporary",
                "--http-enabled",
                "--https-enabled=false",
            ],
            ports=port_bindings, # type: ignore
            detach=True,
        ) # type: ignore

    def _fetch_mapped_port(self) -> None:
        if self._container is None:
            raise RuntimeError("Container failed to start")
            
        max_retries, retry_delay = 5, 1
        
        for attempt in range(max_retries):
            try:
                container_info = self._docker_client.api.inspect_container(
                    self._container.id)
                port_mappings = container_info["NetworkSettings"]["Ports"].get(f"{self._internal_port}/tcp")
                
                if port_mappings and "HostPort" in port_mappings[0]:
                    self._mapped_port = int(port_mappings[0]["HostPort"])
                    return
            except (KeyError, IndexError, AttributeError):
                pass
                
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                
        # Failed to get port, clean up
        self._stop_and_remove_container()
        raise RuntimeError("Failed to determine mapped port")

    def _wait_for_http(self, path: str, timeout: int) -> None:
        base_url = self.get_base_url()
        url = f"{base_url}{path}"
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(url, timeout=2)
                if response.status_code == 200:
                    return
            except requests.RequestException:
                pass
            time.sleep(0.5)
        
        self._stop_and_remove_container()
        raise TimeoutError(f"Service failed to become ready within {timeout} seconds")

    def _stop_and_remove_container(self) -> None:
        if self._container is None:
            return
            
        try:    
            self._container.stop()
            self._container.remove()
        except Exception as e:
            print(f"Warning: Error stopping container: {e}")
        finally:
            self._container = None
            self._mapped_port = None

    def get_host(self) -> str:
        if self._container is None:
            raise RuntimeError("Container must be running.")
        return self._host

    def get_mapped_port(self) -> int:
        if self._container is None or self._mapped_port is None:
            raise RuntimeError("Container must be running.")
        return self._mapped_port

    def get_base_url(self) -> str:
        if self._container is None:
            raise RuntimeError("Container must be running.")
        return f"http://{self.get_host()}:{self.get_mapped_port()}"

    def get_api_token(self) -> str:
        return self._api_token

    def is_running(self) -> bool:
        return self._container is not None

    def stop(self) -> None:
        self._stop_and_remove_container()

    def get_client(self) -> Client:
        return Client(self.get_base_url(), self.get_api_token())
