class InternalException(Exception):
	def __init__(self, message, inner_exception=None):
		super().__init__(message)
		self.inner_exception = inner_exception
