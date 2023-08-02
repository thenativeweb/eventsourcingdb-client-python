from collections.abc import Callable, Coroutine
import time
from typing import TypeVar

from .retry_error import RetryError
from .retry_result import RetryResult, Return
from ..get_randomized_duration import get_randomized_duration


ReturnT = TypeVar('ReturnT')


async def retry_with_backoff(
    tries: int,
    operation: Callable[[], Coroutine[None, None, RetryResult[ReturnT]]],
) -> ReturnT:
    if tries < 1:
        raise ValueError('Tries must be greater than 0')

    retry_error = RetryError()

    for tries_count in range(tries):
        timeout = get_randomized_duration(300, 100) * tries_count

        time.sleep(timeout / 1_000)

        result = await operation()

        if isinstance(result, Return):
            return result.data

        retry_error.append_error(result.cause)

    raise retry_error
