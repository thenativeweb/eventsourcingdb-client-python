from .validation_error import ValidationError


class UnsupportedHashVersionError(ValidationError):
    def __init__(self, version: str) -> None:
        super().__init__(f"Hash version '{version}' is not supported.")
        self.version = version
