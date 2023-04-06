from .client_configuration import ClientConfiguration
from .errors.client_error import ClientError
from .errors.custom_error import CustomError
from .errors.internal_error import InternalError
from .errors.server_error import ServerError
from .util import url
from .util.retry.retry_with_backoff import retry_with_backoff, RetryResult, Return, Retry
from .util.retry.retry_error import RetryError
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
			f' client \'{self.__client_configuration.protocol_version}\'.'
		)

	def __get_get_request_headers(self, with_authorization: bool) -> Dict[str, str]:
		headers = {
			'X-EventSourcingDB-Protocol-Version': self.__client_configuration.protocol_version,
		}

		if with_authorization:
			headers['Authorization'] = f'Bearer {self.__client_configuration.access_token}'

		return headers

	def get(self, path: str, with_authorization: bool = True) -> requests.Response:
		try:

			def execute_request() -> RetryResult[requests.Response]:
				response = requests.get(
					url.join_segments(self.__client_configuration.base_url, path),
					timeout=self.__client_configuration.timeout_seconds,
					headers=self.__get_get_request_headers(with_authorization)
				)

				if 500 <= response.status_code < 600:
					return Retry(ServerError(f'Request failed with status code \'{response.status_code}\'.'))

				if 400 <= response.status_code < 500:
					raise ClientError(f'Request failed with status code \'{response.status_code}\'.')

				self.__validate_protocol_version(response.status_code, response.headers)

				return Return(response)

			return retry_with_backoff(
				self.__client_configuration.max_tries,
				execute_request
			)
		except RetryError as retry_error:
			raise ServerError(retry_error.__str__())
		except CustomError as custom_error:
			raise custom_error
		except requests.exceptions.RequestException as request_error:
			raise ServerError(request_error.__str__())
		except Exception as other_error:
			raise InternalError(other_error.__str__())

