from dataclasses import dataclass
from typing import Any


@dataclass
class ReadSubjectsOptions:
    # Required, since neither reading the subject alone nor reading it with
    # all its nested subjects is the obvious choice.
    recursive: bool

    def to_json(self) -> dict[str, Any]:
        return {"recursive": self.recursive}
