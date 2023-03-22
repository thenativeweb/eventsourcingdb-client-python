from .client import Client
from .errors.client_error import ClientError
from .util import url
from http import HTTPStatus
import requests
from requests.structures import CaseInsensitiveDict

Headers = CaseInsensitiveDict[str]


class HttpClient:
    def __init__(self, database_client: Client):
        self.database_client: Client = database_client

    def __validate_protocol_version(self, http_status_code: int, headers: Headers) -> None:
        if http_status_code != HTTPStatus.UNPROCESSABLE_ENTITY:
            return

        server_protocol_version = headers.get('x-eventsourcingdb-protocol-version')

        if server_protocol_version is None:
            server_protocol_version = 'unknown version'

        raise ClientError(
            f'Protocol version mismatch, server \'{server_protocol_version}\','
            f' client \'{self.database_client.configuration.protocolVersion}\'.'
        )

    def get(self, path: str) -> requests.Response:
        response = requests.get(url.join_segments(self.database_client.configuration.baseUrl, path))

        self.__validate_protocol_version(response.status_code, response.headers)

        return response
