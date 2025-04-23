import json
from enum import Enum
from typing import Any

from eventsourcingdb.handlers.bound import Bound

class EventSourcingDBJSONEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Bound):
            return o.to_dict()
        elif isinstance(o, Enum):
            return o.value
        return super().default(o)
