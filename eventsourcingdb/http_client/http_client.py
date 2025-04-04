from collections import namedtuple
from collections.abc import Callable, Coroutine
from http import HTTPStatus

import aiohttp
from aiohttp import ClientSession

from .response import Response, Headers
from ..client_configuration import ClientConfiguration
from ..errors.client_error import ClientError
from ..errors.custom_error import CustomError
from ..errors.internal_error import InternalError
from ..errors.server_error import ServerError
from ..util import url
from ..util.retry.retry_result import Retry, Return, RetryResult
from ..util.retry.retry_with_backoff import retry_with_backoff
from ..util.retry.retry_error import RetryError

Range = namedtuple('Range', 'lower, upper')


class UninitializedError(CustomError):
    pass


class HttpClient:
    def __init__(
        self,
        client_configuration: ClientConfiguration
    ):
        self.__client_configuration: ClientConfiguration = client_configuration
        self.__session: ClientSession | None = None

    async def initialize(self) -> None:
        self.__session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(
                connect=self.__client_configuration.timeout_seconds,
                sock_read=self.__client_configuration.timeout_seconds
            )
        )

    async def close(self):
        if self.__session is not None:
            await self.__session.close()

    async def __execute_request(
        self,
        execute_request: Callable[[], Coroutine[None, None, RetryResult[Response]]]
    ) -> Response:
        try:
            return await retry_with_backoff(
                self.__client_configuration.max_tries,
                execute_request
            )
        except RetryError as retry_error:
            raise ServerError(str(retry_error)) from retry_error
        except CustomError as custom_error:
            raise custom_error
        except aiohttp.ClientError as request_error:
            raise ServerError(str(request_error)) from request_error
        except Exception as other_error:
            raise InternalError(str(other_error)) from other_error

    def __validate_protocol_version(self, http_status_code: int, headers: Headers) -> None:
        if http_status_code != HTTPStatus.UNPROCESSABLE_ENTITY:
            return

        server_protocol_version = headers.get(
            'x-eventsourcingdb-protocol-version'
        )

        if server_protocol_version is None:
            server_protocol_version = 'unknown version'

        raise ClientError(
            f'Protocol version mismatch, server \'{server_protocol_version}\','
            f' client \'{self.__client_configuration.protocol_version}\'.'
        )

    @staticmethod
    async def __get_error_message(response: Response):
        error_message = f'Request failed with status code \'{response.status_code}\''

        # We want to purposefully ignore all errors here, as we're already error handling,
        # and this function just tries to get more information on a best-effort basis.
        # pylint: disable=too-many-try-statements
        try:
            encoded_error_reason = await response.body.read()
            error_reason = encoded_error_reason.decode('utf-8')
            error_message += f" {error_reason}"
        finally:
            pass
        # pylint: enable=too-many-try-statements

        error_message += '.'

        return error_message

    async def __validate_response(
        self,
        response: Response
    ) -> RetryResult[Response]:
        server_failure_range = Range(500, 600)
        if server_failure_range.lower <= response.status_code < server_failure_range.upper:
            return Retry(ServerError(await self.__get_error_message(response)))

        client_failure_range = Range(400, 500)
        if client_failure_range.lower <= response.status_code < client_failure_range.upper:
            raise ClientError(await self.__get_error_message(response))

        self.__validate_protocol_version(response.status_code, response.headers)

        return Return(response)

    def __get_post_request_headers(self) -> dict[str, str]:
        headers = {
            'X-EventSourcingDB-Protocol-Version': self.__client_configuration.protocol_version,
            'Authorization': f'Bearer {self.__client_configuration.access_token}',
            'Content-Type': 'application/json'
        }

        return headers

    async def post(self, path: str, request_body: str) -> Response:
        if self.__session is None:
            raise UninitializedError()

        async def execute_request() -> RetryResult[Response]:
            response = await self.__session.post(
                url.join_segments(
                    self.__client_configuration.base_url,
                    path
                ),
                data=request_body,
                headers=self.__get_post_request_headers(),
            )

            response = Response(response)
            try:
                result = await self.__validate_response(response)
            except Exception as error:
                response.close()
                raise error

            if isinstance(result, Retry):
                response.close()

            return result

        return await self.__execute_request(execute_request)

    def __get_get_request_headers(self, with_authorization: bool) -> dict[str, str]:
        headers = {
            'X-EventSourcingDB-Protocol-Version': self.__client_configuration.protocol_version,
        }

        if with_authorization:
            headers['Authorization'] = f'Bearer {self.__client_configuration.access_token}'

        return headers

    async def get(
        self,
        path: str,
        with_authorization: bool = True,
    ) -> Response:
        if self.__session is None:
            raise UninitializedError()

        async def execute_request() -> RetryResult[Response]:
            response = await self.__session.get(
                url.join_segments(
                    self.__client_configuration.base_url, path),
                headers=self.__get_get_request_headers(with_authorization),
            )

            response = Response(response)
            try:
                result = await self.__validate_response(response)
            except Exception as error:
                response.close()
                raise error

            if isinstance(result, Retry):
                response.close()

            return result

        return await self.__execute_request(execute_request)
