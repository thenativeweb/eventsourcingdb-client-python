from http import HTTPStatus
import json
from ..abstract_base_client import AbstractBaseClient
from ..errors.server_error import ServerError

# Define constants for response values
OK_RESPONSE = "OK"
STATUS_OK = "ok"

async def ping(client: AbstractBaseClient) -> None:
    response = await client.http_client.get('/api/v1/ping')
    response_body = bytes.decode(await response.body.read(), encoding='utf-8')

    if response.status_code != HTTPStatus.OK:
        raise ServerError(f'Received unexpected response: {response_body}')
        
    # Check old format (plain "OK")
    if response_body == OK_RESPONSE:
        return
        
    # Check new format (JSON {"status":"ok"})
    try:
        response_json = json.loads(response_body)
        if isinstance(response_json, dict) and response_json.get('status') == STATUS_OK:
            return
    except json.JSONDecodeError:
        pass
        
    raise ServerError(f'Received unexpected response: {response_body}')
