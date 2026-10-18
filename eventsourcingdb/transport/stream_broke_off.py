from ..errors import ServerError


def stream_broke_off() -> ServerError:
    """
    The error for a stream that the server closed before it ended: a stream
    of the v2 API that has not sent its end item yet, or an observation, which
    never ends, since the server closes it only after an unexpected failure.
    A graceful shutdown, in contrast, sends an error item first.
    """
    return ServerError('The server closed the stream before it ended, so it is incomplete.')
