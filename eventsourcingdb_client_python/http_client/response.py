import asyncio
from collections.abc import Mapping
from http import HTTPStatus

import aiohttp

Headers = Mapping[str, str]


class Response:
    def __init__(self, response: aiohttp.ClientResponse):
        self.__response: aiohttp.ClientResponse = response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return True

    def close(self):
        self.close()

    @property
    def status_code(self) -> HTTPStatus:
        return HTTPStatus(self.__response.status)

    @property
    def headers(self) -> Headers:
        return self.__response.headers

    @property
    def body(self) -> asyncio.StreamReader:
        return self.body
