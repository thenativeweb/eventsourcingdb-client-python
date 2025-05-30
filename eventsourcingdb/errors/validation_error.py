from .custom_error import CustomError


class ValidationError(CustomError):
    def __init__(self, cause: str) -> None:
        super().__init__(f'Validation error occurred: {cause}')
