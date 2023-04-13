from ...errors.custom_error import CustomError


class RetryError(CustomError):
    def __init__(self):
        self.__errors = []

    def append_error(self, error: Exception):
        super().__init__()
        self.__errors.append(error)

    def __str__(self) -> str:
        return (
            f'Failed operation with {len(self.__errors)} error(s):\n'
            '\n'.join(str(self.__errors))
        )
