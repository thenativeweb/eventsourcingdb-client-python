from dataclasses import dataclass
from typing import Any


@dataclass
class PreconditionOptions:
    recursive: bool

    def to_json(self) -> dict[str, Any]:
        return {"recursive": self.recursive}
