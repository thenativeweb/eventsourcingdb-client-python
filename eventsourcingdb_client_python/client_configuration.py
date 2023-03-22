from dataclasses import dataclass


@dataclass
class ClientConfiguration:
    baseUrl: str
    timeoutMilliseconds: int = 10_000
    accessToken: str = ''
    protocolVersion: str = '1.0.0'
    maxTries: int = 10
