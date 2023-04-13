from .shared.build_database import build_database
from .shared.database import Database
from .shared.event.test_source import test_source
from .shared.start_local_http_server import AttachHandler, StopServer, Response, start_local_http_server
from eventsourcingdb_client_python.errors.client_error import ClientError
from eventsourcingdb_client_python.errors.invalid_parameter_error import InvalidParameterError
from eventsourcingdb_client_python.errors.server_error import ServerError
from eventsourcingdb_client_python.event.event_candidate import EventCandidate
from eventsourcingdb_client_python.handlers.read_subjects import ReadSubjectsOptions
from http import HTTPStatus
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
			for _ in client.read_subjects():
				pass

	def test_supports_authorization(self):
		client = TestReadSubjects.database.with_authorization.client

		for _ in client.read_subjects():
			pass

	def test_reads_all_subjects_starting_from_root(self):
		client = TestReadSubjects.database.with_authorization.client

		client.write_events([
			EventCandidate(test_source, '/foo', 'io.thenativeweb.user.janeDoe.loggedIn', {})
		])

		actual_subjects = [subject for subject in client.read_subjects()]

		assert actual_subjects == ['/', '/foo']

	def test_reads_all_subjects_starting_from_given_base_subject(self):
		client = TestReadSubjects.database.with_authorization.client

		client.write_events([
			EventCandidate(test_source, '/foo/bar', 'io.thenativeweb.user.janeDoe.loggedIn', {})
		])

		actual_subjects = [subject for subject in client.read_subjects(ReadSubjectsOptions('/foo'))]

		assert actual_subjects == ['/foo', '/foo/bar']

	def test_throws_an_error_if_base_subject_malformed(self):
		client = TestReadSubjects.database.with_authorization.client

		client.write_events([
			EventCandidate(test_source, '/foo/bar', 'io.thenativeweb.user.janeDoe.loggedIn', {})
		])

		with pytest.raises(InvalidParameterError):
			for _ in client.read_subjects(ReadSubjectsOptions('')):
				pass


class TestReadSubjectsWithMockServer:
	stop_server: StopServer = lambda: None

	@staticmethod
	def teardown_method():
		TestReadSubjectsWithMockServer.stop_server()

	def test_throws_error_if_server_responds_with_5xx_status_code(self):
		def attach_handlers(attach_handler: AttachHandler):
			def handle_read_subjects(response: Response) -> Response:
				response.status_code = HTTPStatus.BAD_GATEWAY
				response.set_data(HTTPStatus.BAD_GATEWAY.phrase)
				return response

			attach_handler('/api/read-subjects', 'POST', handle_read_subjects)

		client, stop_server = start_local_http_server(attach_handlers)
		TestReadSubjectsWithMockServer.stop_server = stop_server

		with pytest.raises(ServerError):
			for _ in client.read_subjects():
				pass

	def test_throws_error_if_servers_protocol_version_not_matching(self):
		def attach_handlers(attach_handler: AttachHandler):
			def handle_read_subjects(response: Response) -> Response:
				response.headers['X-EventSourcingDB-Protocol-Version'] = '0.0.0'
				response.status_code = HTTPStatus.UNPROCESSABLE_ENTITY
				response.set_data(HTTPStatus.UNPROCESSABLE_ENTITY.phrase)
				return response

			attach_handler('/api/read-subjects', 'POST', handle_read_subjects)

		client, stop_server = start_local_http_server(attach_handlers)
		TestReadSubjectsWithMockServer.stop_server = stop_server

		with pytest.raises(ClientError):
			for _ in client.read_subjects():
				pass

	def test_throws_error_if_server_responds_with_4xx_status_code(self):
		def attach_handlers(attach_handler: AttachHandler):
			def handle_read_subjects(response: Response) -> Response:
				response.status_code = HTTPStatus.NOT_FOUND
				response.set_data(HTTPStatus.NOT_FOUND.phrase)
				return response

			attach_handler('/api/read-subjects', 'POST', handle_read_subjects)

		client, stop_server = start_local_http_server(attach_handlers)
		TestReadSubjectsWithMockServer.stop_server = stop_server

		with pytest.raises(ClientError):
			for _ in client.read_subjects():
				pass

	def test_throws_error_if_server_responds_with_unusual_status_code(self):
		def attach_handlers(attach_handler: AttachHandler):
			def handle_read_subjects(response: Response) -> Response:
				response.status_code = HTTPStatus.ACCEPTED
				response.set_data('{"type": "subject", "payload": { "subject": "/foo" }}')
				return response

			attach_handler('/api/read-subjects', 'POST', handle_read_subjects)

		client, stop_server = start_local_http_server(attach_handlers)
		TestReadSubjectsWithMockServer.stop_server = stop_server

		with pytest.raises(ServerError):
			for _ in client.read_subjects():
				pass

	def test_throws_error_if_server_responds_with_item_that_cannot_be_unmarshalled(self):
		def attach_handlers(attach_handler: AttachHandler):
			def handle_read_subjects(response: Response) -> Response:
				response.status_code = HTTPStatus.OK
				response.set_data('cannot be parsed')
				return response

			attach_handler('/api/read-subjects', 'POST', handle_read_subjects)

		client, stop_server = start_local_http_server(attach_handlers)
		TestReadSubjectsWithMockServer.stop_server = stop_server

		with pytest.raises(ServerError):
			for _ in client.read_subjects():
				pass

	def test_throws_error_if_server_responds_with_unsupported_item(self):
		def attach_handlers(attach_handler: AttachHandler):
			def handle_read_subjects(response: Response) -> Response:
				response.status_code = HTTPStatus.OK
				response.set_data('{ "type": "clown", "payload": { "task": "emotional support" }')
				return response

			attach_handler('/api/read-subjects', 'POST', handle_read_subjects)

		client, stop_server = start_local_http_server(attach_handlers)
		TestReadSubjectsWithMockServer.stop_server = stop_server

		with pytest.raises(ServerError):
			for _ in client.read_subjects():
				pass

	def test_throws_error_if_server_responds_with_an_error_item(self):
		def attach_handlers(attach_handler: AttachHandler):
			def handle_read_subjects(response: Response) -> Response:
				response.status_code = HTTPStatus.OK
				response.set_data('{ "type": "error", "payload": { "error": "some error happened" }')
				return response

			attach_handler('/api/read-subjects', 'POST', handle_read_subjects)

		client, stop_server = start_local_http_server(attach_handlers)
		TestReadSubjectsWithMockServer.stop_server = stop_server

		with pytest.raises(ServerError):
			for _ in client.read_subjects():
				pass
