from .custom_error import CustomError


class OutcomeUnknownError(CustomError):
    """
    Writing events or registering an event schema failed in a way that leaves
    open whether the server stored the write, such as a connection that broke
    after the request was sent. Since EventSourcingDB never stores a write
    halfway, the write was either stored completely or not at all. The cause
    is the error that the write failed with.
    """

    def __init__(self, cause: BaseException) -> None:
        description = f"{type(cause).__name__}: {cause}" if str(cause) else type(cause).__name__
        super().__init__(f"The write may have been stored, its outcome is unknown: {description}")
        self.cause = cause
