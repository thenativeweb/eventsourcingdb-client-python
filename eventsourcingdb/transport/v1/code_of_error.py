from http import HTTPStatus

from ...errors import ErrorCode

WRITE_EVENTS_PATH = '/api/v1/write-events'
REGISTER_EVENT_SCHEMA_PATH = '/api/v1/register-event-schema'
READ_EVENT_TYPE_PATH = '/api/v1/read-event-type'
READ_EVENTS_PATH = '/api/v1/read-events'

# The texts with which EventSourcingDB 1.2 reports errors that clearly match
# a code of the v2 API, per path and status. A text matches if the text that
# the server sends starts with it, since some go on, such as with the reason
# why an event does not match a schema. A text of None matches every text.
CODES_BY_TEXT: dict[tuple[str | None, int], list[tuple[str | None, ErrorCode]]] = {
    (WRITE_EVENTS_PATH, HTTPStatus.CONFLICT): [
        ('state conflict: precondition failed', ErrorCode.PRECONDITION_VIOLATED),
        ('state conflict: exceeded max store capacity', ErrorCode.CAPACITY_EXCEEDED),
        (
            'schema conflict: event candidate does not match schema',
            ErrorCode.EVENT_SCHEMA_VIOLATED,
        ),
    ],
    (REGISTER_EVENT_SCHEMA_PATH, HTTPStatus.CONFLICT): [
        ('schema conflict: schema already exists', ErrorCode.EVENT_SCHEMA_ALREADY_REGISTERED),
        ('schema conflict: event with ID', ErrorCode.EVENT_SCHEMA_VIOLATED),
    ],
    (READ_EVENTS_PATH, HTTPStatus.CONFLICT): [
        (
            'state conflict: fromLatestEvent results in an event ID greater than upperBound ID',
            ErrorCode.RANGE_UNSATISFIABLE,
        ),
    ],
    (READ_EVENT_TYPE_PATH, HTTPStatus.NOT_FOUND): [
        (None, ErrorCode.EVENT_TYPE_UNKNOWN),
    ],
    # Every path.
    (None, HTTPStatus.SERVICE_UNAVAILABLE): [
        (
            'the current operation mode conflicts with the given request',
            ErrorCode.STORE_READ_ONLY,
        ),
    ],
    (WRITE_EVENTS_PATH, HTTPStatus.INSUFFICIENT_STORAGE): [
        (None, ErrorCode.LICENSE_INVALID),
    ],
}


def code_of_error(path: str, status: int, text: str) -> str | None:
    """
    Returns the code of the v2 API for an error of the v1 API that clearly
    matches one, and None for every other error.
    """
    for candidate_path in (path, None):
        for start, code in CODES_BY_TEXT.get((candidate_path, status), []):
            if start is None or text.startswith(start):
                return code.value

    return None
