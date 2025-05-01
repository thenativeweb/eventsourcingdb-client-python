from collections.abc import Mapping
from http import HTTPStatus

import aiohttp
from aiohttp import StreamReader

Headers = Mapping[str, str]


class Response:
    def __init__(self, response: aiohttp.ClientResponse):
        self.__response: aiohttp.ClientResponse = response

    async def __aenter__(self):
        # Properly await any async initialization if needed
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if not self.__response.closed:
            self.__response.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
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

    def __str__(self) -> str:
        return f'Response(status_code={self.status_code}, headers={dict(self.headers)})'
