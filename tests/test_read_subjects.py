from .shared.build_database import build_database
from .shared.database import Database
from eventsourcingdb_client_python.errors.server_error import ServerError
import pytest


class TestReadSubjects:
	database: Database

	@classmethod
	def setup_class(cls):
		build_database('tests/shared/docker/eventsourcingdb')

	@staticmethod
	def setup_method():
		TestReadSubjects.database = Database()

	@staticmethod
	def teardown_method():
		TestReadSubjects.database.stop()

	def test_throws_error_if_server_is_not_reachable(self):
		client = TestReadSubjects.database.with_invalid_url.client

		with pytest.raises(ServerError):
			client.read_subjects()
