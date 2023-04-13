from collections import namedtuple
from dataclasses import dataclass
from http import HTTPStatus

import requests
from requests.structures import CaseInsensitiveDict

from .client_configuration import ClientConfiguration
from .errors.client_error import ClientError
from .errors.custom_error import CustomError
from .errors.internal_error import InternalError
from .errors.server_error import ServerError
from .util import url
from .util.retry.retry_with_backoff import retry_with_backoff, RetryResult, Return, Retry
from .util.retry.retry_error import RetryError

Headers = CaseInsensitiveDict[str]
Range = namedtuple('Range', 'lower, upper')

@dataclass
class HttpClient:
    client_configuration: ClientConfiguration

    def __validate_protocol_version(self, http_status_code: int, headers: Headers) -> None:
        if http_status_code != HTTPStatus.UNPROCESSABLE_ENTITY:
            return

        server_protocol_version = headers.get(
            'x-eventsourcingdb-protocol-version')

        if server_protocol_version is None:
            server_protocol_version = 'unknown version'

        raise ClientError(
            f'Protocol version mismatch, server \'{server_protocol_version}\','
            f' client \'{self.client_configuration.protocol_version}\'.'
        )

    def __validate_response(self, response: requests.Response) -> RetryResult[requests.Response]:
        server_failure_range = Range(500, 600)
        if server_failure_range.lower <= response.status_code < server_failure_range.upper:
            return Retry(
                ServerError(f'Request failed with status code \'{response.status_code}\'.')
            )

        client_failure_range = Range(400, 500)
        if client_failure_range.lower <= response.status_code < client_failure_range.upper:
            raise ClientError(
                f'Request failed with status code \'{response.status_code}\'.')

        self.__validate_protocol_version(
            response.status_code, response.headers)

        return Return(response)

    def __get_post_request_headers(self) -> dict[str, str]:
        headers = {
            'X-EventSourcingDB-Protocol-Version': self.client_configuration.protocol_version,
            'Authorization': f'Bearer {self.client_configuration.access_token}',
            'Content-Type': 'application/json'
        }

        return headers

    def post(self, path: str, request_body: str, stream_response: bool = False):
        def execute_request() -> RetryResult[requests.Response]:
            response = requests.post(
                url.join_segments(
                    self.client_configuration.base_url, path),
                timeout=self.client_configuration.timeout_seconds,
                headers=self.__get_post_request_headers(),
                data=request_body,
                stream=stream_response
            )

            return self.__validate_response(response)

        try:
            return retry_with_backoff(
                self.client_configuration.max_tries,
                execute_request
            )
        except RetryError as retry_error:
            raise ServerError(str(retry_error)) from retry_error
        except CustomError as custom_error:
            raise custom_error
        except requests.exceptions.RequestException as request_error:
            raise ServerError(str(request_error)) from request_error
        except Exception as other_error:
            raise InternalError(str(other_error)) from other_error

    def __get_get_request_headers(self, with_authorization: bool) -> dict[str, str]:
        headers = {
            'X-EventSourcingDB-Protocol-Version': self.client_configuration.protocol_version,
        }

        if with_authorization:
            headers['Authorization'] = f'Bearer {self.client_configuration.access_token}'

        return headers

    def get(
        self,
        path: str,
        with_authorization: bool = True,
        stream_response: bool = False
    ) -> requests.Response:
        def execute_request() -> RetryResult[requests.Response]:
            response = requests.get(
                url.join_segments(
                    self.client_configuration.base_url, path),
                timeout=self.client_configuration.timeout_seconds,
                headers=self.__get_get_request_headers(with_authorization),
                stream=stream_response
            )

            return self.__validate_response(response)

        try:
            return retry_with_backoff(
                self.client_configuration.max_tries,
                execute_request
            )
        except RetryError as retry_error:
            raise ServerError(str(retry_error)) from retry_error
        except CustomError as custom_error:
            raise custom_error
        except requests.exceptions.RequestException as request_error:
            raise ServerError(str(request_error)) from request_error
        except Exception as other_error:
            raise InternalError(str(other_error)) from other_error
