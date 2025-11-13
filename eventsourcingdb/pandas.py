from typing import AsyncGenerator

import pandas as pd

from .event.event import Event

__all__ = ["events_to_dataframe"]


async def events_to_dataframe(events: AsyncGenerator[Event, None]) -> pd.DataFrame:
    """
    Convert an async stream of events to a pandas DataFrame.

    All event fields are included as columns. The 'data' field remains
    as a dict column - use pd.json_normalize() for flattening if needed.

    Args:
        events: An async generator of Event objects

    Returns:
        A pandas DataFrame with all event fields as columns
    """
    event_list = []

    async for event in events:
        event_dict = {
            "event_id": event.event_id,
            "time": event.time,
            "source": event.source,
            "subject": event.subject,
            "type": event.type,
            "data": event.data,
            "spec_version": event.spec_version,
            "data_content_type": event.data_content_type,
            "predecessor_hash": event.predecessor_hash,
            "hash": event.hash,
            "trace_parent": event.trace_parent,
            "trace_state": event.trace_state,
            "signature": event.signature,
        }
        event_list.append(event_dict)

    if len(event_list) == 0:
        return pd.DataFrame(
            columns=[
                "event_id",
                "time",
                "source",
                "subject",
                "type",
                "data",
                "spec_version",
                "data_content_type",
                "predecessor_hash",
                "hash",
                "trace_parent",
                "trace_state",
                "signature",
            ]
        )

    return pd.DataFrame(event_list)
