from dataclasses import dataclass
from enum import Enum


class BoundType(str, Enum):
    INCLUSIVE = "inclusive"
    EXCLUSIVE = "exclusive"


@dataclass
class Bound:
    id: str
    type: BoundType

    def to_json(self) -> dict[str, str]:
        return {
            'id': self.id,
            'type': self.type.value
        }
