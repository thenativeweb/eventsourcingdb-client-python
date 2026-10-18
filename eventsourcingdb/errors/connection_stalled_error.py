from .server_error import ServerError


class ConnectionStalledError(ServerError):
    def __init__(self, stall_timeout: float) -> None:
        super().__init__(self._describe(stall_timeout))
        self.stall_timeout = stall_timeout

    @staticmethod
    def _describe(stall_timeout: float) -> str:
        return f"Nothing arrived from the server for {stall_timeout:g} seconds"
