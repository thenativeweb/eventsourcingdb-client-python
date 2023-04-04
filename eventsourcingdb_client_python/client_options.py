from dataclasses import dataclass


@dataclass
class ClientOptions:
    timeoutSeconds: int = 10
    accessToken: str = ''
    protocolVersion: str = '1.0.0'
    maxTries: int = 10
