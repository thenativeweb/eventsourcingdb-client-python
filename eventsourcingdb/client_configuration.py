from dataclasses import dataclass


@dataclass
class ClientConfiguration:
    base_url: str
    api_token: str
