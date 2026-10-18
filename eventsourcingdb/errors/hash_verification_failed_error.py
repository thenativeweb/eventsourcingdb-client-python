from .validation_error import ValidationError


class HashVerificationFailedError(ValidationError):
    def __init__(self) -> None:
        super().__init__("Failed to verify hash.")
