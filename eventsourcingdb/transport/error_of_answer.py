from collections.abc import Callable
from http import HTTPStatus

from ..errors import DbApiError
from ..http_client import Response

CodeOf = Callable[[int, str], str | None]


def without_code(_: int, __: str) -> str | None:
    return None


async def error_of_answer(response: Response, code_of: CodeOf = without_code) -> DbApiError:
    """
    Turns an answer with a status other than 200, whose body is a text, into
    the error that the server reports with it. The given function finds the
    code of the error from its status and its text, if there is one.
    """
    body = await response.read()
    description = body.decode('utf-8', errors='replace').strip()

    return DbApiError(
        status=response.status,
        description=description,
        code=code_of(response.status, description),
        retry_after=get_retry_after(response),
    )


def get_retry_after(response: Response) -> int | None:
    """
    Returns the seconds to wait before trying again, which only an answer with
    status 429 tells, and only if it has a Retry-After header in seconds.
    """
    if response.status != HTTPStatus.TOO_MANY_REQUESTS:
        return None

    retry_after = response.headers.get('Retry-After', '').strip()
    if not retry_after.isascii() or not retry_after.isdigit():
        return None

    return int(retry_after)
