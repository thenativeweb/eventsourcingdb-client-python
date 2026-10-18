import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import TracebackType
from typing import Self

from aiohttp import web

from eventsourcingdb import Client

WriteStream = Callable[[web.StreamResponse], Awaitable[None]]


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
    """

    def __init__(
        self,
        write_stream: WriteStream | None,
        stall_timeout: float | None = None,
        *,
        status: int = 200,
        headers: Mapping[str, str | None] | None = None,
    ) -> None:
        self.__write_stream = write_stream
        self.__stall_timeout = stall_timeout
        self.__status = status
        self.__headers: dict[str, str] = {
            name: value
            for name, value in {
                'Server': 'EventSourcingDB/test',
                'Content-Type': 'application/x-ndjson',
                **(headers or {}),
            }.items()
            if value is not None
        }
        self.__runner: web.AppRunner | None = None
        self.__client: Client | None = None
        self.client_disconnected = asyncio.Event()
        self.requests: list[ReceivedRequest] = []

    async def __aenter__(self) -> Self:
        application = web.Application()
        application.router.add_route('*', '/{path:.*}', self.__handle)

        # Cancelling the handler when the client disconnects is what lets
        # tests notice that the client closed the connection.
        self.__runner = web.AppRunner(application, handler_cancellation=True)
        await self.__runner.setup()
        await web.TCPSite(self.__runner, '127.0.0.1', 0).start()
        host, port = self.__runner.addresses[0][:2]

        if self.__stall_timeout is None:
            self.__client = Client(base_url=f'http://{host}:{port}', api_token='secret')
        else:
            self.__client = Client(
                base_url=f'http://{host}:{port}',
                api_token='secret',
                stall_timeout=self.__stall_timeout,
            )
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

    def get_client(self) -> Client:
        if self.__client is None:
            raise RuntimeError('Stream server must be started before getting a client.')

        return self.__client

    async def __handle(self, request: web.Request) -> web.StreamResponse:
        try:
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
