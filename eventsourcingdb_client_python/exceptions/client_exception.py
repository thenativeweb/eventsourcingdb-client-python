class ClientException(Exception):
    def __int__(self, cause: str):
        super().__init__(f'Client exception occurred: {cause}')
