from dataclasses import dataclass


@dataclass
class ClientConfiguration:
    base_url: str
    timeout_seconds: int
    api_token: str
    protocol_version: str
    max_tries: int
