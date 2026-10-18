from .connection_stalled_error import ConnectionStalledError


class HeartbeatTimeoutError(ConnectionStalledError):
    # The default is the default stall timeout, so that the error can still be
    # created without an argument.
    def __init__(self, stall_timeout: float = 30) -> None:
        super().__init__(stall_timeout)

    @staticmethod
    def _describe(stall_timeout: float) -> str:
        return f"No event and no heartbeat arrived for {stall_timeout:g} seconds"
