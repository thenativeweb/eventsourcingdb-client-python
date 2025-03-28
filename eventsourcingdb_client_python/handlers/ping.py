from http import HTTPStatus
import json

from ..abstract_base_client import AbstractBaseClient
from ..errors.server_error import ServerError

async def ping(client: AbstractBaseClient) -> None:
    response = await client.http_client.get('/api/v1/ping')
    response_body = bytes.decode(await response.body.read(), encoding='utf-8')

    try:
        response_json = json.loads(response_body)
    except json.JSONDecodeError:
        pass
    else:
        if isinstance(response_json, dict) and response_json.get('status') == 'ok':
            return None
    raise ServerError(f'Received unexpected response: {response_body}')