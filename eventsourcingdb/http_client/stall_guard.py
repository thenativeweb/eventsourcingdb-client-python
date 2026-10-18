import asyncio
from types import SimpleNamespace, TracebackType
from typing import Any, Self

import aiohttp

from .request_state import RequestState

DEFAULT_STALL_TIMEOUT_SECONDS = 30


class StallGuard:
    """
    Ends a request once nothing has arrived from the server for the stall
    timeout, from sending the request until the response headers arrive. Its
    clock starts with the request, keeps running while the request waits for
    a free connection of the pool, so that no request waits forever, and
    restarts once the connection is open. While the body of the response
    arrives, Response takes over.
    """

    def __init__(self, stall_timeout: float, request_state: RequestState | None = None) -> None:
        self.__stall_timeout = stall_timeout
        self.__timeout: asyncio.Timeout | None = None
        self.__request_state = request_state
        self.is_waiting_for_connection = False
        self.is_connected = False

    async def __aenter__(self) -> Self:
        self.__timeout = asyncio.timeout(self.__stall_timeout)
        await self.__timeout.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        if self.__timeout is None:
            return None
        return await self.__timeout.__aexit__(exc_type, exc_val, exc_tb)

    def expired(self) -> bool:
        return self.__timeout is not None and self.__timeout.expired()

    def restart(self) -> None:
        self.__reschedule(asyncio.get_running_loop().time() + self.__stall_timeout)

    def mark_connected(self) -> None:
        self.is_connected = True
        if self.__request_state is not None:
            self.__request_state.is_connected = True
        self.restart()

    def __reschedule(self, when: float | None) -> None:
        if self.__timeout is None or self.__timeout.expired():
            return
        self.__timeout.reschedule(when)


def create_stall_trace_config() -> aiohttp.TraceConfig:
    """
    Lets aiohttp tell the stall guard of a request, which is handed over as its
    trace_request_ctx, how the request proceeds.
    """
    trace_config = aiohttp.TraceConfig()
    trace_config.on_connection_queued_start.append(mark_waiting_for_connection)
    trace_config.on_connection_queued_end.append(mark_done_waiting_for_connection)
    trace_config.on_connection_create_end.append(mark_connected)
    trace_config.on_connection_reuseconn.append(mark_connected)

    return trace_config


def get_stall_guard(trace_config_ctx: SimpleNamespace) -> StallGuard | None:
    stall_guard = getattr(trace_config_ctx, 'trace_request_ctx', None)
    if isinstance(stall_guard, StallGuard):
        return stall_guard
    return None


async def mark_waiting_for_connection(
    _: aiohttp.ClientSession, trace_config_ctx: SimpleNamespace, __: Any
) -> None:
    if (stall_guard := get_stall_guard(trace_config_ctx)) is not None:
        stall_guard.is_waiting_for_connection = True


async def mark_done_waiting_for_connection(
    _: aiohttp.ClientSession, trace_config_ctx: SimpleNamespace, __: Any
) -> None:
    if (stall_guard := get_stall_guard(trace_config_ctx)) is not None:
        stall_guard.is_waiting_for_connection = False


async def mark_connected(
    _: aiohttp.ClientSession, trace_config_ctx: SimpleNamespace, __: Any
) -> None:
    if (stall_guard := get_stall_guard(trace_config_ctx)) is not None:
        stall_guard.mark_connected()
