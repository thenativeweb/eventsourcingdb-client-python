from http import HTTPStatus
import json
from ..client import Client
from ..errors.server_error import ServerError

# Define constants for response values
OK_RESPONSE = "OK"
STATUS_OK = "ok"

# CloudEvent field names
SPECVERSION_FIELD = "specversion"
TYPE_FIELD = "type"
PING_RECEIVED_TYPE = "io.eventsourcingdb.api.ping-received"


async def ping(client: Client) -> None:
    response = await client.http_client.get("/api/v1/ping")
    response_body = bytes.decode(await response.body.read(), encoding="utf-8")

    if response.status_code != HTTPStatus.OK:
        raise ServerError(f"Received unexpected response: {response_body}")

    # Check old format (plain "OK")
    if response_body == OK_RESPONSE:
        return

    try:
        response_json = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise ServerError(f"Received unexpected response: {response_body}") from exc

    # Check if it's a CloudEvent format (has specversion, type fields)
    if (
        isinstance(response_json, dict)
        and SPECVERSION_FIELD in response_json
        and TYPE_FIELD in response_json
        and response_json.get(TYPE_FIELD) == PING_RECEIVED_TYPE
    ):
        return


    raise ServerError(f"Received unexpected response: {response_body}")
