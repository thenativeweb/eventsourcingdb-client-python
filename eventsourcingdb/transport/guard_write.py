import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from ..errors import DbApiError, OutcomeUnknownError
from ..http_client import RequestState

T = TypeVar('T')

IsRefusal = Callable[[DbApiError], bool]


async def guard_write(
    write: Callable[[RequestState], Awaitable[T]],
    is_refusal: IsRefusal,
) -> T:
    """
    Makes a write, such as writing events or registering an event schema, and
    tells a failure that leaves open whether the server stored the write by
    raising an OutcomeUnknownError with the failure as its cause.

    The write was certainly not stored only if the request never got a
    connection, such as when the name of the server could not be resolved,
    connecting or TLS failed, or the request waited for a free connection in
    vain, or if the server explicitly refused the write, which the given
    function tells by the error that the server reports. Every other failure
    may come after the server stored the write, so its outcome is unknown.
    This includes the caller cancelling the request once it has a
    connection, since the request may have been sent by then.
    """
    request_state = RequestState()

    try:
        return await write(request_state)
    except (Exception, asyncio.CancelledError) as error:
        if not request_state.is_connected:
            raise
        if isinstance(error, DbApiError) and is_refusal(error):
            raise

        raise OutcomeUnknownError(error) from error
