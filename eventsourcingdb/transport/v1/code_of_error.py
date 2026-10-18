from http import HTTPStatus

from ...errors import ErrorCode

WRITE_EVENTS_PATH = '/api/v1/write-events'
REGISTER_EVENT_SCHEMA_PATH = '/api/v1/register-event-schema'
READ_EVENT_TYPE_PATH = '/api/v1/read-event-type'

# The texts with which EventSourcingDB 1.2 reports these errors. A text may
# go on after them, such as with the reason why an event does not match a
# schema.
OPERATION_MODE_CONFLICTS = 'the current operation mode conflicts with the given request'
PRECONDITION_FAILED = 'state conflict: precondition failed'
SCHEMA_CONFLICT = 'schema conflict'
SCHEMA_ALREADY_EXISTS = 'schema conflict: schema already exists'


def code_of_error(path: str, status: int, text: str) -> str | None:
    """
    Returns the code of the v2 API for an error of the v1 API that clearly
    matches one, and None for every other error.
    """
    if status == HTTPStatus.SERVICE_UNAVAILABLE and text.startswith(OPERATION_MODE_CONFLICTS):
        return ErrorCode.STORE_READ_ONLY.value

    if path == WRITE_EVENTS_PATH:
        # A text starting with 'state conflict' does not suffice, since the
        # v1 API also reports an exceeded capacity of the store as a state
        # conflict, which is not a precondition that does not hold.
        if status == HTTPStatus.CONFLICT and text.startswith(PRECONDITION_FAILED):
            return ErrorCode.PRECONDITION_VIOLATED.value
        if status == HTTPStatus.CONFLICT and text.startswith(SCHEMA_CONFLICT):
            return ErrorCode.EVENT_SCHEMA_VIOLATED.value
        if status == HTTPStatus.INSUFFICIENT_STORAGE:
            return ErrorCode.LICENSE_INVALID.value

    if (
        path == REGISTER_EVENT_SCHEMA_PATH
        and status == HTTPStatus.CONFLICT
        and text == SCHEMA_ALREADY_EXISTS
    ):
        return ErrorCode.EVENT_SCHEMA_ALREADY_REGISTERED.value

    if path == READ_EVENT_TYPE_PATH and status == HTTPStatus.NOT_FOUND:
        return ErrorCode.EVENT_TYPE_UNKNOWN.value

    return None
