from types import TracebackType

import aiohttp
from aiohttp import ClientSession

from ..errors.custom_error import CustomError
from ..util import url

from .execute_request import execute_request
from .get_get_headers import get_get_headers
from .get_post_headers import get_post_headers
from .response import Response
from .validate_response import validate_response


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
        exc_type: BaseException | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
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

    async def post(self, path: str, request_body: str) -> Response:
        if self.__session is None:
            raise CustomError()

        async def request_executor() -> Response:
            # Vorbereitung
            url_path = url.join_segments(self.__base_url, path)
            headers = get_post_headers(self.__api_token)

            # Request ausführen
            async_response = await self.__session.post(  # type: ignore
                url_path,
                data=request_body,
                headers=headers,
            )

            # Response erstellen
            response = Response(async_response)

            # Split try block to have only one statement
            validated_response = None
            try:
                validated_response = await validate_response(response)
            except Exception as error:
                response.close()
                raise error

            return validated_response

        return await execute_request(request_executor)

    async def get(
        self,
        path: str,
        with_authorization: bool = True,
    ) -> Response:
        if self.__session is None:
            raise CustomError()

        async def request_executor() -> Response:
            # Vorbereitung
            url_path = url.join_segments(self.__base_url, path)
            headers = get_get_headers(self.__api_token, with_authorization)

            # Request ausführen
            async_response = await self.__session.get(  # type: ignore
                url_path,
                headers=headers,
            )

            # Response erstellen
            response = Response(async_response)

            # Split try block to have only one statement
            validated_response = None
            try:
                validated_response = await validate_response(response)
            except Exception as error:
                response.close()
                raise error

            return validated_response

        return await execute_request(request_executor)
