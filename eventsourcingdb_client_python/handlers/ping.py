from http import HTTPStatus

from ..abstract_base_client import AbstractBaseClient
from ..errors.server_error import ServerError


def ping(client: AbstractBaseClient) -> None:
    response = client.http_client.get('/ping')

    if response.status_code != HTTPStatus.OK or response.text != 'OK':
        raise ServerError(f'Received unexpected response: {response.text}')
