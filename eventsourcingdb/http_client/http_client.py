import math
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Self

import aiohttp
from aiohttp import ClientSession

from ..errors.connection_stalled_error import ConnectionStalledError
from .get_get_headers import get_get_headers
from .get_post_headers import get_post_headers
from .response import Response
from .stall_guard import (
    DEFAULT_STALL_TIMEOUT_SECONDS,
    StallGuard,
    create_stall_trace_config,
)

# The stall timeout alone limits a request, so none of the limits of aiohttp
# applies: neither its total of five minutes, which would end a long stream,
# nor its 30 seconds for connecting.
NO_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=None)


class HttpClient:
    def __init__(
        self,
        base_url: str,
        api_token: str,
        stall_timeout: float = DEFAULT_STALL_TIMEOUT_SECONDS,
    ) -> None:
        # There is no way to turn the stall timeout off, since a request would
        # then wait forever for a server that stalls.
        if not math.isfinite(stall_timeout) or stall_timeout <= 0:
            raise ValueError(
                'The stall timeout must be a finite number of seconds greater than zero, '
                f'but is {stall_timeout}.'
            )

        self.__base_url = base_url
        self.__api_token = api_token
        self.__stall_timeout = stall_timeout
        self.__session: ClientSession | None = None

    async def __aenter__(self) -> Self:
        await self.__initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        await self.__close()

    async def __initialize(self) -> None:
        # If a session already exists, close it first to prevent leaks
        if self.__session is not None:
            await self.__session.close()

        self.__session = aiohttp.ClientSession(
            connector_owner=True,
            timeout=NO_TIMEOUT,
            trace_configs=[create_stall_trace_config()],
        )

    async def __close(self) -> None:
        if self.__session is not None:
            await self.__session.close()
            self.__session = None

    @staticmethod
    def join_segments(first: str, *rest: str) -> str:
        first_without_trailing_slash = first.rstrip('/')
        rest_joined = '/'.join([segment.strip('/') for segment in rest])

        return f'{first_without_trailing_slash}/{rest_joined}'

    async def post(
        self,
        path: str,
        request_body: str,
    ) -> Response:
        if self.__session is None:
            await self.__initialize()

        url_path = HttpClient.join_segments(self.__base_url, path)
        headers = get_post_headers(self.__api_token)

        async_response = await self.__send(
            lambda stall_guard: self.__session.post(  # type: ignore
                url_path,
                data=request_body,
                headers=headers,
                trace_request_ctx=stall_guard,
            ),
        )

        return Response(async_response, self.__stall_timeout)

    async def get(
        self,
        path: str,
        with_authorization: bool = True,
    ) -> Response:
        if self.__session is None:
            await self.__initialize()

        url_path = HttpClient.join_segments(self.__base_url, path)
        headers = get_get_headers(self.__api_token, with_authorization)

        async_response = await self.__send(
            lambda stall_guard: self.__session.get(  # type: ignore
                url_path,
                headers=headers,
                trace_request_ctx=stall_guard,
            ),
        )

        return Response(async_response, self.__stall_timeout)

    async def __send(
        self,
        send: Callable[[StallGuard], Awaitable[aiohttp.ClientResponse]],
    ) -> aiohttp.ClientResponse:
        stall_guard = StallGuard(self.__stall_timeout)

        try:
            async with stall_guard:
                return await send(stall_guard)
        except TimeoutError as error:
            # Only the stall guard means that the server stalled, any other
            # timeout, such as one of the caller, is passed on. A stall is a
            # stall wherever it happens: while waiting for a free connection
            # of the pool, while connecting, while sending the request, and
            # while waiting for the response.
            if not stall_guard.expired():
                raise
            raise ConnectionStalledError(self.__stall_timeout) from error
