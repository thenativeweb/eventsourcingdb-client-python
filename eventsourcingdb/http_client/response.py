import asyncio
from collections.abc import AsyncGenerator, Mapping
from http import HTTPStatus
from typing import Self

import aiohttp
from aiohttp import StreamReader

from ..errors.connection_stalled_error import ConnectionStalledError
from .stall_guard import DEFAULT_STALL_TIMEOUT_SECONDS

Headers = Mapping[str, str]


class Response:
    def __init__(
        self,
        response: aiohttp.ClientResponse,
        stall_timeout: float = DEFAULT_STALL_TIMEOUT_SECONDS,
    ) -> None:
        self.__response: aiohttp.ClientResponse = response
        self.__stall_timeout = stall_timeout

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if not self.__response.closed:
            self.__response.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if not self.__response.closed:
            self.__response.close()

    @property
    def status_code(self) -> HTTPStatus:
        return HTTPStatus(self.__response.status)

    @property
    def headers(self) -> Headers:
        return self.__response.headers

    @property
    def body(self) -> StreamReader:
        return self.__response.content

    async def read(self) -> bytes:
        """
        Reads the whole body. Raises a TimeoutError once nothing arrives for
        the stall timeout, as the total timeout of aiohttp did before.
        """
        chunks = []
        try:
            while chunk := await self.__read_chunk(None):
                chunks.append(chunk)
        except BaseException:
            self.__response.close()
            raise

        return b''.join(chunks)

    async def read_lines(
        self,
        stall_error: type[ConnectionStalledError] = ConnectionStalledError,
    ) -> AsyncGenerator[bytes]:
        """
        Reads the body line by line. Raises the given error once nothing
        arrives for the stall timeout. Every chunk restarts the clock, not
        only every line, and the time the caller spends between two lines
        does not count.
        """
        pending = bytearray()

        while chunk := await self.__read_chunk(stall_error):
            pending += chunk

            start = 0
            while (end := pending.find(b'\n', start)) != -1:
                yield bytes(pending[start:end + 1])
                start = end + 1
            del pending[:start]

        if pending:
            yield bytes(pending)

    async def __read_chunk(self, stall_error: type[ConnectionStalledError] | None) -> bytes:
        timeout = asyncio.timeout(self.__stall_timeout)
        try:
            async with timeout:
                return await self.__response.content.readany()
        except TimeoutError as error:
            # Only this timeout means that the server stalled, any other one,
            # such as one of the caller, is passed on.
            if not timeout.expired() or stall_error is None:
                raise
            raise stall_error(self.__stall_timeout) from error

    def __str__(self) -> str:
        status_code_text = f"{self.status_code} {self.status_code.phrase}"
        return f"Response(status={status_code_text}, headers={dict(self.headers)})"
