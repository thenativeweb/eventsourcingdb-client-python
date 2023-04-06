from .custom_error import CustomError


class ClientError(CustomError):
    def __int__(self, cause: str):
        super().__init__(f'Client error occurred: {cause}')
