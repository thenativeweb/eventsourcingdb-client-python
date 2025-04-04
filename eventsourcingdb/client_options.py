from dataclasses import dataclass


@dataclass
class ClientOptions:
    timeout_seconds: int = 10
    protocol_version: str = '1.0.0'
    max_tries: int = 10
