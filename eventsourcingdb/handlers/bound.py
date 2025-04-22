from dataclasses import dataclass
from enum import Enum


class BoundType(Enum):
    INCLUSIVE = "inclusive"
    EXCLUSIVE = "exclusive"


@dataclass
class Bound:
    id: str
    type: BoundType
