class ClientOptions:
	def __init__(self, timeoutMilliseconds=None, accessToken=None, protocolVersion=None, maxTries=None):
		self.timeoutMilliseconds = timeoutMilliseconds
		self.accessToken = accessToken
		self.protocolVersion = protocolVersion
		self.maxTries = maxTries
