import asyncio
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Self

from aiohttp import web

from eventsourcingdb import Client

WriteStream = Callable[[web.StreamResponse], Awaitable[None]]


class StreamServer:
    """
    A local HTTP server that stands in for EventSourcingDB. It answers
    observe-events and run-eventql-query with whatever the given function
    writes to the stream, so that tests can control every single line.
    """

    def __init__(self, write_stream: WriteStream) -> None:
        self.__write_stream = write_stream
        self.__runner: web.AppRunner | None = None
        self.__client: Client | None = None
        self.client_disconnected = asyncio.Event()

    async def __aenter__(self) -> Self:
        application = web.Application()
        application.router.add_post('/api/v1/observe-events', self.__handle)
        application.router.add_post('/api/v1/run-eventql-query', self.__handle)

        # Cancelling the handler when the client disconnects is what lets
        # tests notice that the client closed the connection.
        self.__runner = web.AppRunner(application, handler_cancellation=True)
        await self.__runner.setup()
        await web.TCPSite(self.__runner, '127.0.0.1', 0).start()
        host, port = self.__runner.addresses[0][:2]

        self.__client = Client(base_url=f'http://{host}:{port}', api_token='secret')
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
        response = web.StreamResponse(
            headers={
                'Server': 'EventSourcingDB/test',
                'Content-Type': 'application/x-ndjson',
            },
        )
        await response.prepare(request)

        try:
            await self.__write_stream(response)
        except asyncio.CancelledError:
            self.client_disconnected.set()
            raise

        return response
