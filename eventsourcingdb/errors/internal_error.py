from .custom_error import CustomError


class InternalError(CustomError):
    def __init__(self, cause: str) -> None:
        super().__init__(f'Internal error occurred: {cause}')
