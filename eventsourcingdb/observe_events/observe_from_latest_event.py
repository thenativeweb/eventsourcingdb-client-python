from dataclasses import dataclass
from typing import Any

from .if_event_is_missing_during_observe import IfEventIsMissingDuringObserve


@dataclass
class ObserveFromLatestEvent:
    subject: str
    type: str
    if_event_is_missing: IfEventIsMissingDuringObserve

    def to_json(self) -> dict[str, Any]:
        return {
            'subject': self.subject,
            'type': self.type,
            'ifEventIsMissing': self.if_event_is_missing
        }
