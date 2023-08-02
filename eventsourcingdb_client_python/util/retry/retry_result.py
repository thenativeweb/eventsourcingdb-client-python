from dataclasses import dataclass
from typing import TypeVar, Generic

DataT = TypeVar('DataT')


@dataclass
class Return(Generic[DataT]):
    data: DataT


@dataclass
class Retry:
    cause: Exception


RetryResult = Return[DataT] | Retry
