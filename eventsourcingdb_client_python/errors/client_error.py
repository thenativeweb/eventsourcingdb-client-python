class ClientError(Exception):
    def __int__(self, cause: str):
        super().__init__(f'Client error occurred: {cause}')
