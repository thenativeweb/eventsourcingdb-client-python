from dataclasses import dataclass
from typing import Any

from ..bound import Bound
from .order import Order
from .read_from_latest_event import ReadFromLatestEvent


@dataclass
class ReadEventsOptions:
    recursive: bool
    order: Order | None = None
    lower_bound: Bound | None = None
    upper_bound: Bound | None = None
    from_latest_event: ReadFromLatestEvent | None = None

    def to_json(self) -> dict[str, Any]:
        json: dict[str, Any] = {
            'recursive': self.recursive
        }

        if self.order is not None:
            json['order'] = self.order.value

        if self.lower_bound is not None:
            json['lowerBound'] = {
                'id': str(self.lower_bound.id),
                'type': self.lower_bound.type
            }

        if self.upper_bound is not None:
            json['upperBound'] = {
                'id': str(self.upper_bound.id),
                'type': self.upper_bound.type
            }

        if self.from_latest_event is not None:
            json['fromLatestEvent'] = self.from_latest_event.to_json()

        return json
