from .errors.client_error import ClientError
from .util import url
from http import HTTPStatus
import requests
from requests.structures import CaseInsensitiveDict

Headers = CaseInsensitiveDict[str]


class HttpClient:
	def __init__(self, base_url: str, protocol_version: str):
		self.__base_url: str = base_url
		self.__protocol_version: str = protocol_version

	def __validate_protocol_version(self, http_status_code: int, headers: Headers) -> None:
		if http_status_code != HTTPStatus.UNPROCESSABLE_ENTITY:
			return

		server_protocol_version = headers.get('x-eventsourcingdb-protocol-version')

		if server_protocol_version is None:
			server_protocol_version = 'unknown version'

		raise ClientError(
			f'Protocol version mismatch, server \'{server_protocol_version}\','
			f' client \'{self.__protocol_version}\'.'
		)

	def get(self, path: str) -> requests.Response:
		response = requests.get(url.join_segments(self.__base_url, path))

		self.__validate_protocol_version(response.status_code, response.headers)

		return response
