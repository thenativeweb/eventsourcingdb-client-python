from .server_error import ServerError


class HeartbeatTimeoutError(ServerError):
    def __init__(self) -> None:
        super().__init__("No event and no heartbeat arrived for 30 seconds")
