import asyncio

import pytest
from aiohttp import web

from eventsourcingdb import CustomError

from .shared.requests import ALL_REQUESTS, Request, ping
from .shared.stream_server import Api, StreamServer

GUARD_TIMEOUT_SECONDS = 5
APIS: list[Api] = ['v1', 'v2']
REQUESTS_EXCEPT_PING = [
    pytest.param(api, parameter.values[0], id=f'{api}, {parameter.id}')
    for api in APIS
    for parameter in ALL_REQUESTS
    if parameter.id != 'ping'
]


async def answer_ping_of_the_v1_api(response: web.StreamResponse) -> None:
    await response.write(b'{"specversion":"1.0","type":"io.eventsourcingdb.api.ping-received"}')


async def answer_with_the_end(response: web.StreamResponse) -> None:
    await response.write(b'{"type":"end","data":{}}\n')


class TestAuthorization:
    # The pings need no API token, so the client sends it only with the other
    # requests, which need it.
    @staticmethod
    @pytest.mark.asyncio
    async def test_pings_and_asks_for_the_api_without_an_api_token_on_the_v1_api() -> None:
        async with StreamServer(answer_ping_of_the_v1_api, api='v1') as server:
            await ping(server.get_client())

            assert server.ping_authorizations == [None]
            assert [(request.path, request.authorization) for request in server.requests] == [
                ('/api/v1/ping', None)
            ]

    @staticmethod
    @pytest.mark.asyncio
    async def test_pings_and_asks_for_the_api_without_an_api_token_on_the_v2_api() -> None:
        async with StreamServer(None, api='v2') as server:
            await ping(server.get_client())

            # The ping of the v2 API is the one that asks for the API.
            assert server.ping_authorizations == [None, None]
            assert server.requests == []

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('api', 'request_'), REQUESTS_EXCEPT_PING)
    async def test_sends_the_api_token_with_every_other_request(
        api: Api, request_: Request
    ) -> None:
        async with StreamServer(answer_with_the_end, api=api) as server:
            # What the request returns does not matter here, only what it sent.
            try:
                async with asyncio.timeout(GUARD_TIMEOUT_SECONDS):
                    await request_(server.get_client())
            except CustomError:
                pass

            assert server.ping_authorizations == [None]
            assert [request.authorization for request in server.requests] == ['Bearer secret']
