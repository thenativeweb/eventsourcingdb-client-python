from .docker.container import Container
from .docker.image import Image
from eventsourcingdb_client_python.client import Client
from eventsourcingdb_client_python.client_options import ClientOptions
from typing import List, Tuple


class ContainerizedTestingDatabase:
	def __init__(
			self,
			image: Image,
			command: List[str],
			options: ClientOptions = ClientOptions(),
	):
		self.__command: List[str] = command
		self.__image: Image = image
		container, client = self.__start(options)
		self.__client: Client = client
		self.__container: Container = container

	def __start(self, options: ClientOptions) -> Tuple[Container, Client]:
		container = self.__image.run(self.__command, True, True)
		exposed_port = container.get_exposed_port(3_000)
		base_url = f'http://127.0.0.1:{exposed_port}'
		client = Client(base_url, options)

		client.ping()

		return container, client

	def stop(self) -> None:
		self.__container.kill()

	@property
	def client(self) -> Client:
		return self.__client
