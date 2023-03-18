from .client_options import ClientOptions
from .server_exception import ServerException
from .internal_exception import InternalException
from requests import RequestException, Session

class Client:
	def __init__(self, base_url, options=None):
		self.base_url = base_url.rstrip("/")
		self.options = options or ClientOptions()
		self.http_client = Session()

		if self.options.timeoutMilliseconds is not None:
			self.http_client.timeout = self.options.timeoutMilliseconds / 1000.0
		else:
			self.http_client.timeout = 0

	def ping(self):
		url = f"{self.base_url}/ping"
		try:
			response = self.http_client.get(url)
			if response.status_code == 200 and response.text == "OK":
				return
			else:
				raise ServerException("Received unexpected response.")
		except RequestException as e:
			raise InternalException("Server is down or not responding as expected.", e)
