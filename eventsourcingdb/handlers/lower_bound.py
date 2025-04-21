from dataclasses import dataclass

from eventsourcingdb.errors.invalid_parameter_error import InvalidParameterError

# TODO: one clas for UpperBound and LowerBound
@dataclass
class LowerBound:
    id: str
    type: str # TODO: Enum for'inclusive', 'exclusive'

    # TODO: can be removed
    def __post_init__(self):
        if self.type not in {'inclusive', 'exclusive'}:
            raise InvalidParameterError(
                parameter_name="LowerBound",
                reason='type must be either "inclusive" or "exclusive"'
            )
        if int(self.id) < 0:
            raise InvalidParameterError(
                parameter_name='LowerBound',
                reason='id must be non-negative'
            )
