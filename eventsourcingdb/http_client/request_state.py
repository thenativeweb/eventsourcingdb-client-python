from dataclasses import dataclass


@dataclass
class RequestState:
    """
    Tells how far a request got, so that a failure can tell whether anything
    may have reached the server: once the request has a connection, it may
    have been sent.
    """

    is_connected: bool = False
