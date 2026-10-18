from ..http_client import HttpClient
from .transport import Transport
from .v1.transport import V1Transport


class ChooseTransport:
    """
    The one place that chooses which version of the API the client speaks.
    """

    def __init__(self, http_client: HttpClient) -> None:
        self.__v1_transport = V1Transport(http_client)

    async def get(self) -> Transport:
        return self.__v1_transport
