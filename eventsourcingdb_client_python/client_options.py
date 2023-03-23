from dataclasses import dataclass
from typing import Optional


@dataclass
class ClientOptions:
    timeoutSeconds: Optional[int] = None
    accessToken: Optional[str] = None
    protocolVersion: Optional[str] = None
    maxTries: Optional[int] = None
