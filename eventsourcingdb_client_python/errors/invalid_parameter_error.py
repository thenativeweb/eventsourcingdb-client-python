from .custom_error import CustomError


class InvalidParameterError(CustomError):
	def __init__(self, parameter_name: str, reason: str):
		super().__init__(f'Parameter \'{parameter_name}\' is invalid: {reason}')

