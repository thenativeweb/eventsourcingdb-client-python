from dataclasses import dataclass


@dataclass
class ClientConfiguration:
    baseUrl: str
    timeoutSeconds: int
    accessToken: str
    protocolVersion: str
    maxTries: int
