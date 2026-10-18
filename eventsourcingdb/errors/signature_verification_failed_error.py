from .validation_error import ValidationError


class SignatureVerificationFailedError(ValidationError):
    def __init__(self, cause: str) -> None:
        super().__init__(cause)
