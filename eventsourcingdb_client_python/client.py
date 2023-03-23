from .client_configuration import ClientConfiguration
from .client_options import ClientOptions
from .errors.server_error import ServerError
from .http_client import HttpClient
from http import HTTPStatus


class Client:

	def __init__(
			self,
			base_url: str,
			options: ClientOptions = ClientOptions()
	):
		if options is None:
			self.configuration: ClientConfiguration = ClientConfiguration(
				base_url
			)
		else:
			self.configuration: ClientConfiguration = ClientConfiguration(
				base_url,
				timeoutSeconds=options.timeoutSeconds,
				accessToken=options.accessToken,
				protocolVersion=options.protocolVersion,
				maxTries=options.maxTries
			)

		self.http_client: HttpClient = HttpClient(self.configuration)

	def ping(self) -> None:
		response = self.http_client.get('/ping')

		if response.status_code != HTTPStatus.OK or response.text != 'OK':
			raise ServerError(f'Received unexpected response: {response.text}')
