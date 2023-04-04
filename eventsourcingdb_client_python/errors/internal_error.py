from .custom_error import CustomError


class InternalError(CustomError):
	def __int__(self, cause: str):
		super().__init__(f'Internal error occurred: {cause}')
