from dataclasses import dataclass


@dataclass
class ClientConfiguration:
    baseUrl: str
    timeoutSeconds: int = 10
    accessToken: str = ''
    protocolVersion: str = '1.0.0'
    maxTries: int = 10
