from collections.abc import Callable, Coroutine
from typing import Any

import aiohttp

from ..errors.custom_error import CustomError
from ..errors.internal_error import InternalError
from ..errors.server_error import ServerError
from .response import Response


async def execute_request(
    func: Callable[[], Coroutine[Any, Any, Response]]
) -> Response:
    try:
        return await func()
    except CustomError as custom_error:
        raise custom_error
    except aiohttp.ClientError as request_error:
        raise ServerError(str(request_error)) from request_error
    except Exception as other_error:
        raise InternalError(str(other_error)) from other_error
