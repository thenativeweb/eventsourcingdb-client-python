from dataclasses import dataclass
from typing import Optional


@dataclass
class ClientOptions:
    timeoutMilliseconds: Optional[int]
    accessToken: Optional[str]
    protocolVersion: Optional[str]
    maxTries: Optional[int]