from http import HTTPStatus

from ..abstract_base_client import AbstractBaseClient
from ..errors.server_error import ServerError


async def ping(client: AbstractBaseClient) -> None:
    response = await client.http_client.get('/ping')
    response_body = bytes.decode(await response.body.read(), encoding='utf-8')

    if response.status_code != HTTPStatus.OK or response_body != HTTPStatus.OK.phrase:
        raise ServerError(f'Received unexpected response: {response_body}')
