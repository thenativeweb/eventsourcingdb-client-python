from collections import namedtuple

from ..errors.client_error import ClientError
from ..errors.server_error import ServerError
from .get_error_message import get_error_message
from .response import Response

Range = namedtuple('Range', 'lower, upper')

async def validate_response(response: Response) -> Response:
    server_failure_range = Range(500, 600)
    if server_failure_range.lower <= response.status_code < server_failure_range.upper:
        raise ServerError(await get_error_message(response))

    client_failure_range = Range(400, 500)
    if client_failure_range.lower <= response.status_code < client_failure_range.upper:
        raise ClientError(await get_error_message(response))

    return response
