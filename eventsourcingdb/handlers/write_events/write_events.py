from http import HTTPStatus
import json

from ...abstract_base_client import AbstractBaseClient
from ...errors.custom_error import CustomError
from ...errors.internal_error import InternalError
from ...errors.invalid_parameter_error import InvalidParameterError
from ...errors.server_error import ServerError
from ...errors.validation_error import ValidationError
from ...event.event_candidate import EventCandidate
from ...event.event_context import EventContext
from ...http_client.response import Response
from .preconditions import Precondition


async def write_events(
    client: AbstractBaseClient,
    event_candidates: list[EventCandidate],
    preconditions: list[Precondition]
) -> list[EventContext]:
    if len(event_candidates) < 1:
        raise InvalidParameterError(
            'event_candidates',
            'event_candidates must contain at least one EventCandidate.'
        )

    request_body = json.dumps(
        {
            'events': [event_candidate.to_json() for event_candidate in event_candidates],
            'preconditions': [precondition.to_json() for precondition in preconditions]
        }
    )

    response: Response
    try:
        response = await client.http_client.post(
            path='/api/v1/write-events',
            request_body=request_body,
        )
    except CustomError as custom_error:
        raise custom_error
    except Exception as other_error:
        raise InternalError(str(other_error)) from other_error

    if response.status_code != HTTPStatus.OK:
        raise ServerError(
            f'Unexpected response status: '
            f'{response.status_code} {HTTPStatus(response.status_code).phrase}.'
        )

    response_data = await response.body.read()
    response_data = bytes.decode(response_data, encoding='utf-8')
    try:
        response_data = json.loads(response_data)
    except json.JSONDecodeError as decode_error:
        raise ServerError(str(decode_error)) from decode_error
    except Exception as other_error:
        raise InternalError(str(other_error)) from other_error

    if not isinstance(response_data, list):
        raise ServerError(
            f'Failed to parse response \'{response_data}\' to list.')

    result = []
    for unparsed_event_context in response_data:
        try:
            result.append(EventContext.parse(unparsed_event_context))
        except ValidationError as validation_error:
            raise ServerError(str(validation_error)) from validation_error
        except Exception as other_error:
            raise InternalError(str(other_error)) from other_error

    return result
