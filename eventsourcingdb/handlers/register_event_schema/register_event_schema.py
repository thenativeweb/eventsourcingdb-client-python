import json
from http import HTTPStatus

from ...abstract_base_client import AbstractBaseClient
from ...errors.custom_error import CustomError
from ...errors.internal_error import InternalError
from ...errors.invalid_parameter_error import InvalidParameterError
from ...errors.server_error import ServerError
from ...errors.validation_error import ValidationError
from ...event.validate_type import validate_type
from ...http_client.response import Response


async def register_event_schema(
    client: AbstractBaseClient,
    event_type: str,
    json_schema: str,
) -> None:
    try:
        validate_type(event_type)
    except ValidationError as validation_error:
        raise InvalidParameterError(
            'event_type', str(validation_error)
        ) from validation_error
    except Exception as other_error:
        raise InternalError(str(other_error)) from other_error

    request_body = json.dumps({
        'eventType': event_type,
        'schema': json_schema,
    })

    response: Response
    try:
        response = await client.http_client.post(
            path='/api/register-event-schema',
            request_body=request_body,
        )
    except CustomError as custom_error:
        raise custom_error
    except Exception as other_error:
        raise InternalError(str(other_error)) from other_error

    with response:
        if response.status_code != HTTPStatus.OK:
            raise ServerError(
                'Unexpected response status: '
                f'{response.status_code} {HTTPStatus(response.status_code).phrase}'
            )

    return
