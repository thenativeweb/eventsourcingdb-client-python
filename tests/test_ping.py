import pytest
from .shared.build_database import build_database
from .shared.database import Database


class TestPing:
	database: Database

	@classmethod
	def setup_class(cls):
		build_database('tests/shared/docker/eventsourcingdb')

	@staticmethod
	def setup_method():
		TestPing.database = Database()

	@staticmethod
	def teardown_method():
		TestPing.database.stop()

	def test_supports_authorization(self):
		TestPing.database.with_authorization.client.ping()
