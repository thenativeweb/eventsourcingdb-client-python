from dataclasses import dataclass

from eventsourcingdb.errors.invalid_parameter_error import InvalidParameterError


@dataclass
class UpperBound:
    id: str
    type: str

    def __post_init__(self):
        if self.type not in {"inclusive", "exclusive"}:
            raise InvalidParameterError(
                parameter_name="UpperBound",
                reason='type must be either "inclusive" or "exclusive"',
            )
        if int(self.id) < 0:
            raise InvalidParameterError(
                parameter_name="UpperBound", reason="id must be non-negative"
            )
