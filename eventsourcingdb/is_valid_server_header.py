from .http_client import Response


def is_valid_server_header(response: Response) -> bool:
    server_header = response.headers.get('Server')

    if not server_header:
        return False

    if not server_header.startswith('EventSourcingDB/'):
        return False

    return True
