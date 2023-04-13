from abc import ABC, abstractmethod
from .http_client import HttpClient


class AbstractBaseClient(ABC):
	@property
	@abstractmethod
	def http_client(self) -> HttpClient:
		raise NotImplemented
