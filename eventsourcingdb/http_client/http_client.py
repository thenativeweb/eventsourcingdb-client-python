from types import TracebackType

import aiohttp
from aiohttp import ClientSession

from .get_get_headers import get_get_headers
from .get_post_headers import get_post_headers
from .response import Response


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
        await self.__initialize()
        return self

    async def __aexit__(
        self,
        exc_type: BaseException | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        await self.__close()

    async def __initialize(self) -> None:
        # If a session already exists, close it first to prevent leaks
        if self.__session is not None:
            await self.__session.close()

        self.__session = aiohttp.ClientSession(connector_owner=True)

    async def __close(self):
        if self.__session is not None:
            await self.__session.close()
            self.__session = None

    @staticmethod
    def join_segments(first: str, *rest: str) -> str:
        first_without_trailing_slash = first.rstrip('/')
        rest_joined = '/'.join([segment.strip('/') for segment in rest])

        return f'{first_without_trailing_slash}/{rest_joined}'

    async def post(self, path: str, request_body: str) -> Response:
        if self.__session is None:
            await self.__initialize()

        url_path = HttpClient.join_segments(self.__base_url, path)
        headers = get_post_headers(self.__api_token)

        async_response = await self.__session.post(  # type: ignore
            url_path,
            data=request_body,
            headers=headers,
        )

        response = Response(async_response)

        return response

    async def get(
        self,
        path: str,
        with_authorization: bool = True,
    ) -> Response:
        if self.__session is None:
            await self.__initialize()

        async def __request_executor() -> Response:
            url_path = HttpClient.join_segments(self.__base_url, path)
            headers = get_get_headers(self.__api_token, with_authorization)

            async_response = await self.__session.get(  # type: ignore
                url_path,
                headers=headers,
            )

            response = Response(async_response)

            return response

        return await __request_executor()
