from dataclasses import dataclass
from ..event.event import Event


@dataclass
class StoreItem:
    event: Event
    hash: str
