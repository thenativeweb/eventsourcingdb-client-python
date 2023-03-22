class ServerException(Exception):
    def __int__(self, cause: str):
        super().__init__(f'Server exception occurred: {cause}')
