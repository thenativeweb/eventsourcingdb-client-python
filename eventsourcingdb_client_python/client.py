from .client_configuration import ClientConfiguration
from .client_options import ClientOptions
from .exceptions.server_exception import ServerException
from .http_client import HttpClient
from http import HTTPStatus
from typing import Optional


class Client:

    def __init__(self, base_url: str, options: Optional[ClientOptions]):
        if options is None:
            self.configuration: ClientConfiguration = ClientConfiguration(
                base_url
            )
        else:
            self.configuration: ClientConfiguration = ClientConfiguration(
                base_url,
                timeoutMilliseconds=options.timeoutMilliseconds,
                accessToken=options.accessToken,
                protocolVersion=options.protocolVersion,
                maxTries=options.maxTries
            )

        self.http_client: HttpClient = HttpClient(self)

    def ping(self) -> None:
        response = self.http_client.get('/path')

        if response.status_code != HTTPStatus.OK or response.text != 'OK':
            raise ServerException('Received unexpected response.')
