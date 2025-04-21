import asyncio
from collections.abc import Mapping
from http import HTTPStatus

import aiohttp
from aiohttp import streams as aiohttp_streams

Headers = Mapping[str, str]


class Response:
    def __init__(self, response: aiohttp.ClientResponse):
        self.__response: aiohttp.ClientResponse = response

    def __aenter__(self):
        return self

    def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self.__response.close()

    @property
    def status_code(self) -> HTTPStatus:
        return HTTPStatus(self.__response.status)

    @property
    def headers(self) -> Headers:
        return self.__response.headers
    @property
    def body(self) -> aiohttp_streams.StreamReader:
        return self.__response.content
