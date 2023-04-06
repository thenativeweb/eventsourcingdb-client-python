from .retry_error import RetryError
import time
import random
from typing import Callable, Generic, TypeVar, Union

TReturn = TypeVar('TReturn')
TData = TypeVar('TData')


class Return(Generic[TData]):
	def __init__(self, data: TData):
		self.data = data


class Retry:
	def __init__(self, cause: Exception):
		self.cause = cause


RetryResult = Union[Return[TReturn], Retry]


def get_randomized_duration(
		duration_milliseconds: int,
		deviation_milliseconds: int
) -> int:
	return duration_milliseconds - deviation_milliseconds + round(random.random() * deviation_milliseconds * 2)


def retry_with_backoff(tries: int, fn: Callable[[], RetryResult]) -> TReturn:
	if tries < 1:
		raise ValueError('Tries must be greater than 0')

	retry_error = RetryError()

	for tries_count in range(tries):
		timeout = get_randomized_duration(100, 25) * tries_count

		time.sleep(timeout / 1_000)

		result = fn()

		if isinstance(result, Return):
			return result.data

		else:
			retry_error.append_error(result.cause)

	raise retry_error


