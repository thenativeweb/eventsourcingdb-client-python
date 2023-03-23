from .client_configuration import ClientConfiguration
from .errors.client_error import ClientError
from .util import url
from http import HTTPStatus
import requests
from requests.structures import CaseInsensitiveDict
from typing import Dict

Headers = CaseInsensitiveDict[str]



class HttpClient:
	def __init__(self, client_configuration: ClientConfiguration):
		self.__client_configuration: ClientConfiguration = client_configuration

	def __validate_protocol_version(self, http_status_code: int, headers: Headers) -> None:
		if http_status_code != HTTPStatus.UNPROCESSABLE_ENTITY:
			return

		server_protocol_version = headers.get('x-eventsourcingdb-protocol-version')

		if server_protocol_version is None:
			server_protocol_version = 'unknown version'

		raise ClientError(
			f'Protocol version mismatch, server \'{server_protocol_version}\','
			f' client \'{self.__client_configuration.protocolVersion}\'.'
		)

	def __get_get_request_headers(self, with_authorization: bool) -> Dict[str, str]:
		headers = {
			'X-EventSourcingDB-Protocol-Version': self.__client_configuration.protocolVersion,
		}

		if with_authorization:
			headers['Authorization'] = f'Bearer {self.__client_configuration.accessToken}'

		return headers

	def get(self, path: str, with_authorization: bool = True) -> requests.Response:
		response = requests.get(
			url.join_segments(self.__client_configuration.baseUrl, path),
			timeout=self.__client_configuration.timeoutSeconds,
			headers=self.__get_get_request_headers(with_authorization)
		)

		self.__validate_protocol_version(response.status_code, response.headers)

		return response
