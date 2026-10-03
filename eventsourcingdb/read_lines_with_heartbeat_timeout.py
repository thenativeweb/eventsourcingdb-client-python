import asyncio
from collections.abc import AsyncGenerator

from aiohttp import StreamReader

from .errors import HeartbeatTimeoutError

HEARTBEAT_TIMEOUT_SECONDS = 30


async def read_lines_with_heartbeat_timeout(stream: StreamReader) -> AsyncGenerator[bytes, None]:
    while True:
        timeout = asyncio.timeout(HEARTBEAT_TIMEOUT_SECONDS)
        try:
            async with timeout:
                line = await stream.readline()
        except TimeoutError as error:
            # Only this timeout means that the server went silent, any other
            # timeout (for example the one of the HTTP session) is passed on.
            if not timeout.expired():
                raise
            raise HeartbeatTimeoutError() from error

        if line == b'':
            return

        yield line
