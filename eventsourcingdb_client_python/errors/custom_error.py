class CustomError(Exception):
	def message(self):
		return self.__str__()
