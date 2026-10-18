import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from ...errors import DbApiError, ServerError
from ...http_client import Response
from ...is_valid_server_header import is_valid_server_header
from ..error_of_answer import error_of_answer
from ..stream_broke_off import stream_broke_off

# The types of the envelopes that the v2 API wraps everything it sends in.
ERROR_TYPE = 'error'
HEARTBEAT_TYPE = 'heartbeat'
END_TYPE = 'end'


@dataclass
class Envelope:
    type: str
    data: Any
    # The line the envelope was sent in, in which the data of an event is
    # found exactly as the server sent it, once its hash is verified.
    raw: bytes


async def ensure_answer_is_ok(response: Response) -> None:
    """
    Ensures that the answer comes from EventSourcingDB and has status 200, and
    raises the error that the server reports otherwise, which the v2 API sends
    as a text without a code for every status other than 200.
    """
    if not is_valid_server_header(response):
        raise ServerError('Server must be EventSourcingDB')
    if response.status != HTTPStatus.OK:
        raise await error_of_answer(response)


def parse_envelope(raw: bytes) -> Envelope:
    try:
        envelope = json.loads(raw.decode('utf-8'))
    except Exception as error:
        raise ServerError(f'Failed to parse the answer of the server: {error}') from error

    if (
        not isinstance(envelope, dict)
        or not isinstance(envelope.get('type'), str)
        or 'data' not in envelope
    ):
        raise ServerError(f'Received an unexpected answer: {envelope}.')

    if envelope['type'] == ERROR_TYPE:
        raise error_of_envelope(envelope['data'])

    return Envelope(type=envelope['type'], data=envelope['data'], raw=raw)


def error_of_envelope(data: Any) -> DbApiError:
    """
    Turns the data of an error envelope, which reports an error in an answer
    with status 200, into the error that the server reports with it.
    """
    if not isinstance(data, dict):
        data = {}

    code = data.get('code')
    description = data.get('description')
    details = data.get('details')

    return DbApiError(
        status=HTTPStatus.OK,
        description=description if isinstance(description, str) else '',
        code=code if isinstance(code, str) else None,
        details=details if isinstance(details, dict) else None,
    )


async def read_envelope(response: Response) -> Envelope:
    """Reads an answer that consists of a single envelope."""
    await ensure_answer_is_ok(response)

    return parse_envelope(await response.read())


async def read_envelopes(response: Response, *, ends: bool = True) -> AsyncGenerator[Envelope]:
    """
    Reads an answer that is a stream of envelopes, one per line, and yields
    every envelope except heartbeats. An error envelope raises the error it
    reports. A stream ends with an end envelope, so one that the server closes
    before raises an error, since it is incomplete. An observation never ends,
    so for it, an end envelope is yielded like any other, and its stream
    always raises that error once the server closes it.
    """
    await ensure_answer_is_ok(response)

    async for raw in response.read_lines():
        envelope = parse_envelope(raw)

        if envelope.type == HEARTBEAT_TYPE:
            continue
        if envelope.type == END_TYPE and ends:
            return

        yield envelope

    raise stream_broke_off()


def unexpected_envelope(envelope: Envelope) -> ServerError:
    return ServerError(f'Received an unexpected item: {envelope.raw.decode("utf-8").strip()}.')
