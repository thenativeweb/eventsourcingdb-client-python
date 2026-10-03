import asyncio
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Self

from aiohttp import web

Handle = Callable[[web.Request], Awaitable[web.StreamResponse]]

HEARTBEAT_LINE = b'{"type":"heartbeat","payload":{}}\n'
HEARTBEAT_INTERVAL_SECONDS = 1


class LocalServer:
    """
    A local HTTP server that stands in for EventSourcingDB. It answers a
    single path with the given handler, so that tests can control how slowly
    a request gets answered.
    """

    def __init__(self, path: str, handle: Handle) -> None:
        self.__path = path
        self.__handle = handle
        self.__runner: web.AppRunner | None = None
        self.__base_url: str | None = None

    async def __aenter__(self) -> Self:
        application = web.Application()
        application.router.add_post(self.__path, self.__handle)

        # Cancelling the handler when the client disconnects lets a handler
        # wait forever without holding up the shutdown of the server.
        self.__runner = web.AppRunner(application, handler_cancellation=True)
        await self.__runner.setup()
        await web.TCPSite(self.__runner, "127.0.0.1", 0).start()
        host, port = self.__runner.addresses[0][:2]
        self.__base_url = f"http://{host}:{port}"

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        if self.__runner is not None:
            await self.__runner.cleanup()

    def get_base_url(self) -> str:
        if self.__base_url is None:
            raise RuntimeError("Local server must be started before getting its base URL.")

        return self.__base_url


async def never_answer(_: web.Request) -> web.StreamResponse:
    await asyncio.Event().wait()

    return web.Response()


async def send_heartbeats_only(request: web.Request) -> web.StreamResponse:
    response = web.StreamResponse(
        headers={
            "Server": "EventSourcingDB/test",
            "Content-Type": "application/x-ndjson",
        },
    )
    await response.prepare(request)

    while True:
        await response.write(HEARTBEAT_LINE)
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
