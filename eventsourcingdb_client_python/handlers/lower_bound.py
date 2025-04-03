from dataclasses import dataclass

@dataclass
class LowerBound:
    id: int
    type: str

    def __post_init__(self):
        if self.type not in {"inclusive", "exclusive"}:
            raise ValueError("type must be either 'inclusive' or 'exclusive'")