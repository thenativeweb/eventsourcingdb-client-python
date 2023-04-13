from .custom_error import CustomError


class ServerError(CustomError):
    def __init__(self, cause: str):
        super().__init__(f'Server error occurred: {cause}')
