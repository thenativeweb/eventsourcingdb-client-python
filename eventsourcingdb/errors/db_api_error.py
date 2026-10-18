from typing import Any

from .server_error import ServerError


class DbApiError(ServerError):
    """
    Everything that EventSourcingDB reports as an error, whether it reports it
    as an error item at status 200, as another status with a text, or through
    the v1 API.
    """

    def __init__(
        self,
        *,
        status: int,
        description: str,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(description or f"The server answered with status {status}")

        # The code is the URL exactly as the server sends it, which matches one
        # of the constants of ErrorCode for every code the client SDK knows,
        # and None for an error that has no code.
        self.code = code
        self.description = description
        self.details: dict[str, Any] = {} if details is None else details
        self.status = status
        # Only an answer with status 429 tells how many seconds to wait before
        # trying again, and only if it has a Retry-After header.
        self.retry_after = retry_after
