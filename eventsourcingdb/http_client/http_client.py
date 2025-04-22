from collections import namedtuple
from collections.abc import Callable, Coroutine
from types import TracebackType
from typing import Any, Optional, Type

import aiohttp
from aiohttp import ClientSession

from .response import Response
from ..errors.client_error import ClientError
from ..errors.custom_error import CustomError
from ..errors.internal_error import InternalError
from ..errors.server_error import ServerError
from ..util import url

Range = namedtuple('Range', 'lower, upper')


class UninitializedError(CustomError):
    pass


class HttpClient:
    def __init__(
        self,
        base_url: str,
        api_token: str,
    ):
        self.__base_url = base_url
        self.__api_token = api_token
        self.__session: ClientSession | None = None
    
    async def __aenter__(self):
        await self.initialize()
        return self
    
    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType]
    ) -> None:
        await self.close()

    # Keep for backward compatibility
    async def initialize(self) -> None:
        self.__session = aiohttp.ClientSession()

    # Keep for backward compatibility
    async def close(self):
        if self.__session is not None:
            await self.__session.close()
            self.__session = None
        return None 

    async def __execute_request(
        self,
        execute_request: Callable[[], Coroutine[Any, Any, Response]]
    ) -> Response:
        try:
            result = await execute_request()
            return result
        except CustomError as custom_error:
            raise custom_error
        except aiohttp.ClientError as request_error:
            raise ServerError(str(request_error)) from request_error
        except Exception as other_error:
            raise InternalError(str(other_error)) from other_error


    @staticmethod
    async def __get_error_message(response: Response):
        error_message = f'Request failed with status code \'{response.status_code}\''

        # We want to purposefully ignore all errors here, as we're already error handling,
        # and this function just tries to get more information on a best-effort basis.
        try:
            encoded_error_reason = await response.body.read()
            error_reason = encoded_error_reason.decode('utf-8')
            error_message += f" {error_reason}"
        finally:
            pass

        error_message += '.'

        return error_message

    async def __validate_response(
        self,
        response: Response
    ) -> Response:
        server_failure_range = Range(500, 600)
        if server_failure_range.lower <= response.status_code < server_failure_range.upper:
            raise ServerError(await self.__get_error_message(response))

        client_failure_range = Range(400, 500)
        if client_failure_range.lower <= response.status_code < client_failure_range.upper:
            raise ClientError(await self.__get_error_message(response))

        return response

    def __get_post_request_headers(self) -> dict[str, str]:
        headers = {
            'Authorization': f'Bearer {self.__api_token}',
            'Content-Type': 'application/json'
        }

        return headers

    async def post(self, path: str, request_body: str) -> Response:
        if self.__session is None:
            raise UninitializedError()

        async def execute_request() -> Response:
            async_response = await self.__session.post( # type: ignore
                url.join_segments(
                    self.__base_url,
                    path
                ),
                data=request_body,
                headers=self.__get_post_request_headers(),
            )

            response = Response(async_response)
            try:
                result = await self.__validate_response(response)
                return result
            except Exception as error:
                response.close()
                raise error

        return await self.__execute_request(execute_request)

    def __get_get_request_headers(self, with_authorization: bool) -> dict[str, str]:
        headers = {}

        if with_authorization:
            headers['Authorization'] = f'Bearer {self.__api_token}'

        return headers

    async def get(
        self,
        path: str,
        with_authorization: bool = True,
    ) -> Response:
        if self.__session is None:
            raise UninitializedError()

        async def execute_request() -> Response:
            async_response = await self.__session.get( # type: ignore
                url.join_segments(
                    self.__base_url, 
                    path
                ),
                headers=self.__get_get_request_headers(with_authorization),
            )

            response = Response(async_response)
            try:
                result = await self.__validate_response(response)
                return result
            except Exception as error:
                response.close()
                raise error

        return await self.__execute_request(execute_request)
