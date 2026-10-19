import asyncio

from .outcome_unknown_error import OutcomeUnknownError

# How a cancelled write whose outcome is unknown is marked: by this attribute,
# which outcome_is_unknown queries, and by this note, which tracebacks show.
# A cancellation is not wrapped in an OutcomeUnknownError, so that it still
# cancels as asyncio expects, for example in asyncio.timeout and TaskGroup.
OUTCOME_UNKNOWN_ATTRIBUTE = 'eventsourcingdb_outcome_unknown'
OUTCOME_UNKNOWN_NOTE = (
    'The write may have been stored, since it was cancelled after it had a connection.'
)


def mark_outcome_unknown(cancellation: asyncio.CancelledError) -> None:
    """Marks a cancelled write whose outcome is unknown."""
    setattr(cancellation, OUTCOME_UNKNOWN_ATTRIBUTE, True)
    cancellation.add_note(OUTCOME_UNKNOWN_NOTE)


def outcome_is_unknown(error: BaseException) -> bool:
    """
    Tells whether the error leaves open whether a write was stored: it is an
    OutcomeUnknownError, a cancellation of a write after it had a connection,
    or an error caused by one of them, such as the TimeoutError that
    asyncio.timeout raises once it cancels such a write.
    """
    seen: set[int] = set()
    pending: list[BaseException] = [error]

    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))

        if isinstance(current, OutcomeUnknownError):
            return True
        if getattr(current, OUTCOME_UNKNOWN_ATTRIBUTE, False) is True:
            return True

        pending.extend(
            linked for linked in (current.__cause__, current.__context__) if linked is not None
        )

    return False
