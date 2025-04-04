from dataclasses import dataclass

from eventsourcingdb_client_python.errors.invalid_parameter_error import InvalidParameterError


@dataclass
class UpperBound:
    id: int
    type: str

    def __post_init__(self):
        if self.type not in {'inclusive', 'exclusive'}:
            raise InvalidParameterError(
                parameter_name='UpperBound',
                reason='type must be either "inclusive" or "exclusive"'
            )