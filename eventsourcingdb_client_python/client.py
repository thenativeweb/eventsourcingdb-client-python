from .abstract_base_client import AbstractBaseClient
from .client_configuration import ClientConfiguration
from .client_options import ClientOptions
from .http_client import HttpClient
from .handlers.ping import ping
from .handlers.read_subjects import read_subjects, ReadSubjectsOptions


class Client(AbstractBaseClient):

	def __init__(
			self,
			base_url: str,
			options: ClientOptions = ClientOptions()
	):
		self.configuration: ClientConfiguration = ClientConfiguration(
			base_url=base_url,
			timeout_seconds=options.timeout_seconds,
			access_token=options.access_token,
			protocol_version=options.protocol_version,
			max_tries=options.max_tries
		)

		self.__http_client: HttpClient = HttpClient(self.configuration)

	@property
	def http_client(self) -> HttpClient:
		return self.__http_client

	def ping(self) -> None:
		return ping(self)

	def read_subjects(self, options: ReadSubjectsOptions = ReadSubjectsOptions()) -> str:
		return read_subjects(self, options)
