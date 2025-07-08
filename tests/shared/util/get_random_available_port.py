import socket


def get_random_available_port() -> int:
    socket_ = socket.socket()
    socket_.bind(("", 0))
    port = socket_.getsockname()[1]
    socket_.close()

    return port
