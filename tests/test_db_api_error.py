import json

import pytest
from aiohttp import web

from eventsourcingdb import (
    DbApiError,
    ErrorCode,
    ServerError,
)

from .shared.requests import (
    ALL_REQUESTS,
    Request,
    ping,
    read_event_type,
    read_events,
    register_event_schema,
    verify_api_token,
    write_events,
)
from .shared.stream_server import StreamServer

TEXT_PLAIN = {'Content-Type': 'text/plain; charset=utf-8'}
OPERATION_MODE_CONFLICTS = (
    'the current operation mode conflicts with the given request: writing is not permitted'
)


def answer_with(text: str, status: int, headers: dict[str, str | None] | None = None) -> StreamServer:
    async def write_stream(response: web.StreamResponse) -> None:
        await response.write(text.encode('utf-8'))

    return StreamServer(write_stream, status=status, headers={**TEXT_PLAIN, **(headers or {})})


async def error_of(request_: Request, server: StreamServer) -> DbApiError:
    async with server:
        with pytest.raises(DbApiError) as error:
            await request_(server.get_client())

    return error.value


class TestDbApiError:
    @staticmethod
    def test_is_a_server_error() -> None:
        error = DbApiError(status=409, description='state conflict: precondition failed')

        assert isinstance(error, ServerError)
        assert str(error) == 'Server error occurred: state conflict: precondition failed'

    @staticmethod
    def test_has_no_code_and_empty_details_unless_given() -> None:
        error = DbApiError(status=500, description='')

        assert error.code is None
        assert error.details == {}
        assert error.retry_after is None
        assert str(error) == 'Server error occurred: The server answered with status 500'


class TestErrorsOfTheV1Api:
    # The texts as EventSourcingDB 1.2 sends them, followed by a line feed.
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ('request_', 'status', 'text', 'expected_code'),
        [
            pytest.param(
                write_events,
                409,
                'state conflict: precondition failed',
                ErrorCode.PRECONDITION_VIOLATED,
                id='write_events, failed precondition',
            ),
            pytest.param(
                write_events,
                409,
                "schema conflict: event candidate does not match schema: missing properties: 'n'",
                ErrorCode.EVENT_SCHEMA_VIOLATED,
                id='write_events, violated schema',
            ),
            pytest.param(
                register_event_schema,
                409,
                'schema conflict: schema already exists',
                ErrorCode.EVENT_SCHEMA_ALREADY_REGISTERED,
                id='register_event_schema, registered schema',
            ),
            pytest.param(
                read_event_type,
                404,
                "event type 'io.eventsourcingdb.library.book-acquired' not found",
                ErrorCode.EVENT_TYPE_UNKNOWN,
                id='read_event_type, unknown event type',
            ),
            pytest.param(
                write_events,
                507,
                'insufficient storage',
                ErrorCode.LICENSE_INVALID,
                id='write_events, insufficient storage',
            ),
        ]
        + [
            pytest.param(
                *parameter.values,
                503,
                OPERATION_MODE_CONFLICTS,
                ErrorCode.STORE_READ_ONLY,
                id=f'{parameter.id}, conflicting operation mode',
            )
            for parameter in ALL_REQUESTS
        ],
    )
    async def test_assigns_the_code_of_the_v2_api_to_errors_that_clearly_match_one(
        request_: Request, status: int, text: str, expected_code: ErrorCode
    ) -> None:
        error = await error_of(request_, answer_with(f'{text}\n', status))

        assert error.code == expected_code
        assert error.status == status
        assert error.description == text
        assert error.details == {}

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ('request_', 'status', 'text'),
        [
            # An exceeded capacity is a state conflict as well, but no
            # precondition that does not hold.
            pytest.param(
                write_events,
                409,
                'state conflict: exceeded max store capacity',
                id='write_events, exceeded capacity',
            ),
            pytest.param(
                register_event_schema,
                409,
                "schema conflict: event with ID 0: missing properties: 'n'",
                id='register_event_schema, schema conflicting with events',
            ),
            pytest.param(
                read_event_type,
                409,
                'state conflict: precondition failed',
                id='read_event_type, state conflict',
            ),
            pytest.param(
                read_events, 404, 'event type not found', id='read_events, not found'
            ),
            pytest.param(
                register_event_schema,
                507,
                'insufficient storage',
                id='register_event_schema, insufficient storage',
            ),
            pytest.param(
                write_events,
                503,
                'the store is rebuilding its indexes',
                id='write_events, other unavailability',
            ),
            pytest.param(
                write_events, 400, 'bad request: subject is invalid', id='write_events, bad request'
            ),
            pytest.param(verify_api_token, 401, 'unauthorized', id='verify_api_token, unauthorized'),
            pytest.param(write_events, 500, '', id='write_events, internal server error'),
        ],
    )
    async def test_assigns_no_code_to_other_errors(
        request_: Request, status: int, text: str
    ) -> None:
        error = await error_of(request_, answer_with(f'{text}\n', status))

        assert error.code is None
        assert error.status == status
        assert error.description == text

    @staticmethod
    @pytest.mark.asyncio
    async def test_reports_an_error_item_of_a_stream_without_a_code() -> None:
        async def write_stream(response: web.StreamResponse) -> None:
            line = json.dumps({'type': 'error', 'payload': {'error': 'something went wrong'}})
            await response.write(line.encode('utf-8') + b'\n')

        error = await error_of(read_events, StreamServer(write_stream))

        assert error.status == 200
        assert error.code is None
        assert error.description == 'something went wrong'


class TestRetryAfter:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize('request_', ALL_REQUESTS)
    async def test_tells_the_seconds_of_the_retry_after_header_of_a_429(
        request_: Request,
    ) -> None:
        error = await error_of(
            request_, answer_with('too many requests', 429, {'Retry-After': '7'})
        )

        assert error.status == 429
        assert error.description == 'too many requests'
        assert error.retry_after == 7

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ('status', 'headers'),
        [
            pytest.param(429, {}, id='429 without Retry-After'),
            pytest.param(
                429, {'Retry-After': 'Wed, 21 Oct 2026 07:28:00 GMT'}, id='429 with a date'
            ),
            pytest.param(429, {'Retry-After': '-1'}, id='429 with negative seconds'),
            pytest.param(503, {'Retry-After': '7'}, id='503 with Retry-After'),
        ],
    )
    async def test_tells_nothing_without_seconds_or_for_another_status(
        status: int, headers: dict[str, str | None]
    ) -> None:
        error = await error_of(ping, answer_with('unavailable', status, headers))

        assert error.status == status
        assert error.retry_after is None
