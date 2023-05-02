from collections.abc import Callable
from dataclasses import dataclass
import time
import random
from typing import Generic, TypeVar

from .retry_error import RetryError

ReturnT = TypeVar('ReturnT')
DataT = TypeVar('DataT')


@dataclass
class Return(Generic[DataT]):
    data: DataT


@dataclass
class Retry:
    cause: Exception


RetryResult = Return[ReturnT] | Retry


def get_randomized_duration(
    duration_milliseconds: int,
    deviation_milliseconds: int
) -> int:
    return duration_milliseconds \
        - deviation_milliseconds \
        + round(random.random() * deviation_milliseconds * 2)


def retry_with_backoff(tries: int, operation: Callable[[], RetryResult]) -> ReturnT:
    if tries < 1:
        raise ValueError('Tries must be greater than 0')

    retry_error = RetryError()

    for tries_count in range(tries):
        timeout = get_randomized_duration(200, 50) * tries_count

        time.sleep(timeout / 1_000)

        result = operation()

        if isinstance(result, Return):
            return result.data

        retry_error.append_error(result.cause)

    raise retry_error
