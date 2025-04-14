import json
from http import HTTPStatus
from typing import Any

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
    json_schema: str | dict[str, Any],
) -> None:
    try:
        validate_type(event_type)
    except ValidationError as validation_error:
        raise InvalidParameterError(
            'event_type', str(validation_error)
        ) from validation_error
    except Exception as other_error:
        raise InternalError(str(other_error)) from other_error

    # Handle both string and dictionary schema formats
    # If json_schema is a string, parse it to ensure it's valid JSON
    # If it's already a dict, use it directly
    schema_obj = json_schema
    if isinstance(json_schema, str):
        try:
            schema_obj = json.loads(json_schema)
        except json.JSONDecodeError as json_error:
            raise InvalidParameterError(
                'json_schema', f'Invalid JSON schema: {str(json_error)}'
            ) from json_error

    request_body = json.dumps({
        'eventType': event_type,
        'schema': schema_obj,
    })

    response: Response
    try:
        response = await client.http_client.post(
            path='/api/v1/register-event-schema',
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
