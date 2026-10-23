from .custom_error import CustomError


class IncompatibleServerError(CustomError):
    """
    A write has a recursive precondition, which only the v2 API offers, but
    the server does not offer it. The client raises this error before it
    sends the write, so nothing is written.
    """

    def __init__(self) -> None:
        super().__init__(
            "The server does not offer the v2 API, which a recursive precondition needs."
        )
