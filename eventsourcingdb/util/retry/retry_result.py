from dataclasses import dataclass
from typing import TypeVar, Generic

# TODO: Can be removed
DataT = TypeVar('DataT')


@dataclass
class Return(Generic[DataT]):
    data: DataT


@dataclass
class Retry:
    cause: Exception


RetryResult = Return[DataT] | Retry
