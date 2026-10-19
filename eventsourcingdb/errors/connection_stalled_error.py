from .server_error import ServerError


class ConnectionStalledError(ServerError):
    def __init__(self, stall_timeout: float) -> None:
        super().__init__(f"Nothing arrived from the server for {stall_timeout:g} seconds")
        self.stall_timeout = stall_timeout
