class ServerError(Exception):
    def __int__(self, cause: str):
        super().__init__(f'Server error occurred: {cause}')
