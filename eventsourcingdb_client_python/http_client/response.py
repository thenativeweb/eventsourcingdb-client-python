import asyncio
from collections.abc import Mapping
from http import HTTPStatus

import aiohttp

Headers = Mapping[str, str]


class Response:
    def __init__(self, response: aiohttp.ClientResponse, session: aiohttp.ClientSession):
        self.__response: aiohttp.ClientResponse = response
        self.__session: aiohttp.ClientSession = session

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return True

    async def close(self):
        self.__response.close()
        await self.__session.close()

    @property
    def status_code(self) -> HTTPStatus:
        return HTTPStatus(self.__response.status)

    @property
    def headers(self) -> Headers:
        return self.__response.headers

    @property
    def body(self) -> asyncio.StreamReader:
        return self.__response.content
