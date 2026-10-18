import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import TracebackType
from typing import Literal, Self

from aiohttp import web

from eventsourcingdb import Client

WriteStream = Callable[[web.StreamResponse], Awaitable[None]]
AnswerProbe = Callable[[web.Request], Awaitable[web.StreamResponse]]
Api = Literal['v1', 'v2']

PROBE_PATH = '/api/v2/system/ping'
SERVER_HEADER = {'Server': 'EventSourcingDB/test'}
PING_RECEIVED = {
    'type': 'event',
    'data': {
        'specversion': '1.0',
        'id': '01a150c9-6f96-71ef-a309-069f295816c4',
        'source': 'https://www.eventsourcingdb.io',
        'type': 'io.eventsourcingdb.api.ping-received',
        'subject': '/api/v2/system/ping',
        'time': '2026-10-18T20:52:21.0141218Z',
        'datacontenttype': 'application/json',
        'data': {'message': "My God, it's full of stars."},
    },
}


async def answer_probe_without_v2_api(_: web.Request) -> web.StreamResponse:
    # As EventSourcingDB 1.2 answers a path of the v2 API.
    return web.Response(status=404, text='404 page not found\n', headers=SERVER_HEADER)


async def answer_probe_with_v2_api(_: web.Request) -> web.StreamResponse:
    return web.json_response(PING_RECEIVED, headers=SERVER_HEADER)


@dataclass
class ReceivedRequest:
    method: str
    path: str
    body: bytes


class StreamServer:
    """
    A local HTTP server that stands in for EventSourcingDB. It answers every
    request, whatever its method and path, with whatever the given function
    writes to the stream, so that tests can control every single line. Without
    a function, it never answers at all, not even with the response headers.
    It answers with the given status, and with the headers of EventSourcingDB
    unless the given headers replace them, or remove them with None.

    The ping with which a client asks whether the server offers the v2 API is
    answered apart from that, as a server with the given API does, or by the
    given function. It is counted, but not recorded with the other requests.
    If only the first ping is the one the client asks with, any later ping is
    answered like every other request, which tests of the ping itself need.
    """

    def __init__(
        self,
        write_stream: WriteStream | None,
        stall_timeout: float | None = None,
        *,
        status: int = 200,
        headers: Mapping[str, str | None] | None = None,
        api: Api = 'v1',
        answer_probe: AnswerProbe | None = None,
        port: int = 0,
        answers_only_first_probe: bool = False,
    ) -> None:
        self.__answers_only_first_probe = answers_only_first_probe
        self.__port = port
        self.__write_stream = write_stream
        self.__stall_timeout = stall_timeout
        self.__status = status
        self.__headers: dict[str, str] = {
            name: value
            for name, value in {
                **SERVER_HEADER,
                'Content-Type': 'application/x-ndjson',
                **(headers or {}),
            }.items()
            if value is not None
        }
        if answer_probe is None:
            answer_probe = answer_probe_with_v2_api if api == 'v2' else answer_probe_without_v2_api
        self.__answer_probe = answer_probe
        self.__runner: web.AppRunner | None = None
        self.__client: Client | None = None
        self.client_disconnected = asyncio.Event()
        self.requests: list[ReceivedRequest] = []
        self.probe_count = 0

    async def __aenter__(self) -> Self:
        application = web.Application()
        application.router.add_route('*', '/{path:.*}', self.__handle)

        # Cancelling the handler when the client disconnects is what lets
        # tests notice that the client closed the connection.
        self.__runner = web.AppRunner(application, handler_cancellation=True)
        await self.__runner.setup()
        await web.TCPSite(self.__runner, '127.0.0.1', self.__port).start()
        host, port = self.__runner.addresses[0][:2]
        self.base_url = f'http://{host}:{port}'

        self.__client = self.create_client()
        await self.__client.__aenter__()

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        if self.__client is not None:
            await self.__client.__aexit__(exc_type, exc_val, exc_tb)
        if self.__runner is not None:
            await self.__runner.cleanup()

    def create_client(self) -> Client:
        """Creates another client of the server, which has to be closed."""
        if self.__stall_timeout is None:
            return Client(base_url=self.base_url, api_token='secret')

        return Client(
            base_url=self.base_url,
            api_token='secret',
            stall_timeout=self.__stall_timeout,
        )

    def get_client(self) -> Client:
        if self.__client is None:
            raise RuntimeError('Stream server must be started before getting a client.')

        return self.__client

    def last_request_json(self) -> object:
        return json.loads(self.requests[-1].body)

    async def __handle(self, request: web.Request) -> web.StreamResponse:
        try:
            is_probe = request.method == 'GET' and request.path == PROBE_PATH
            if is_probe and not (self.__answers_only_first_probe and self.probe_count > 0):
                self.probe_count += 1
                return await self.__answer_probe(request)

            self.requests.append(
                ReceivedRequest(request.method, request.path, await request.read())
            )

            if self.__write_stream is None:
                await asyncio.Event().wait()

            response = web.StreamResponse(status=self.__status, headers=self.__headers)
            await response.prepare(request)

            await self.__write_stream(response)  # type: ignore
        except asyncio.CancelledError:
            self.client_disconnected.set()
            raise

        return response
