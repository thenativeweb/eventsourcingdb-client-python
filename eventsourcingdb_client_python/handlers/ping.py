from http import HTTPStatus
import json
from ..abstract_base_client import AbstractBaseClient
from ..errors.server_error import ServerError

# Define constants for response values
OK_RESPONSE = "OK"
STATUS_OK = "ok"


async def ping(client: AbstractBaseClient) -> None:
    response = await client.http_client.get("/api/v1/ping")
    response_body = bytes.decode(await response.body.read(), encoding="utf-8")

    if response.status_code != HTTPStatus.OK:
        raise ServerError(f"Received unexpected response: {response_body}")

    # Check old format (plain "OK")
    if response_body == OK_RESPONSE:
        return

    try:
        response_json = json.loads(response_body)
    except json.JSONDecodeError:
        raise ServerError(f"Received unexpected response: {response_body}")

    # Check if it's a JSON with status field
    if isinstance(response_json, dict) and response_json.get("status") == STATUS_OK:
        return

    # Check if it's a CloudEvent format (has specversion, type fields)
    if (
        isinstance(response_json, dict)
        and "specversion" in response_json
        and "type" in response_json
    ):
        if response_json.get("type") == "io.eventsourcingdb.ping-received":
            return

    raise ServerError(f"Received unexpected response: {response_body}")
