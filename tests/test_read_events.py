import pytest

from eventsourcingdb_client_python.event.source import Source
from eventsourcingdb_client_python.handlers.read_events.read_events_options import ReadEventsOptions
from eventsourcingdb_client_python.errors.server_error import ServerError

from .shared.build_database import build_database
from .shared.database import Database
from .shared.event.test_source import TEST_SOURCE


def registered_type(user: str) -> str:
    return f'io.thenativeweb.users.{user}.registered'


def logged_in_type(user: str) -> str:
    return f'io.thenativeweb.users.{user}.loggedIn'


class TestReadEvents:
    database: Database
    source = Source(TEST_SOURCE)
    REGISTERED_SUBJECT = '/users/registered'
    LOGGED_IN_SUBJECT = '/users/loggedIn'
    registered_count = 0
    logged_in_count = 0

    @staticmethod
    def use_registered_subject() -> str:
        TestReadEvents.registered_count += 1
        return TestReadEvents.REGISTERED_SUBJECT

    @staticmethod
    def use_logged_in_subject() -> str:
        TestReadEvents.logged_in_count += 1
        return TestReadEvents.LOGGED_IN_SUBJECT

    @staticmethod
    def total_event_count() -> int:
        return TestReadEvents.registered_count + TestReadEvents.logged_in_count

    @classmethod
    def setup_class(cls):
        build_database('tests/shared/docker/eventsourcingdb')

    @staticmethod
    def setup_method():
        TestReadEvents.database = Database()

        TestReadEvents.database.without_authorization.client.write_events([
            TestReadEvents.source.new_event(
                TestReadEvents.use_registered_subject(),
                registered_type('janeDoe'),
                {}
            ),
            TestReadEvents.source.new_event(
                TestReadEvents.use_logged_in_subject(),
                logged_in_type('janeDoe'),
                {}
            ),
            TestReadEvents.source.new_event(
                TestReadEvents.use_registered_subject(),
                registered_type('johnDoe'),
                {}
            ),
            TestReadEvents.source.new_event(
                TestReadEvents.use_logged_in_subject(),
                logged_in_type('johnDoe'),
                {}
            ),
        ])

    @staticmethod
    def teardown_method():
        TestReadEvents.registered_count = 0
        TestReadEvents.logged_in_count = 0
        TestReadEvents.database.stop()

    @staticmethod
    def test_throws_error_if_server_is_not_reachable():
        client = TestReadEvents.database.with_invalid_url.client

        with pytest.raises(ServerError):
            for _ in client.read_events('/', ReadEventsOptions(recursive=False)):
                pass

    @staticmethod
    def test_supports_authorization():
        client = TestReadEvents.database.with_authorization.client

        for _ in client.read_events('/', ReadEventsOptions(recursive=False)):
            pass

    @staticmethod
    def test_read_events_from_a_single_subject():
        client = TestReadEvents.database.without_authorization.client

        result = []
        for event in client.read_events(
            TestReadEvents.REGISTERED_SUBJECT,
            ReadEventsOptions(recursive=False)
        ):
            result.append(event)

        assert len(result) == TestReadEvents.registered_count
        assert result[0].event.source == TEST_SOURCE
        assert result[0].event.subject == TestReadEvents.REGISTERED_SUBJECT
        assert result[0].event.type == registered_type('janeDoe')
        assert result[1].event.source == TEST_SOURCE
        assert result[1].event.subject == TestReadEvents.REGISTERED_SUBJECT
        assert result[1].event.type == registered_type('johnDoe')

    @staticmethod
    def test_read_events_from_a_subject_including_children():
        client = TestReadEvents.database.without_authorization.client

        result = []
        for event in client.read_events(
            '/users',
            ReadEventsOptions(recursive=True)
        ):
            result.append(event)

        assert len(result) == TestReadEvents.total_event_count()
        assert result[0].event.source == TEST_SOURCE
        assert result[0].event.subject == TestReadEvents.REGISTERED_SUBJECT
        assert result[0].event.type == registered_type('janeDoe')
        assert result[1].event.source == TEST_SOURCE
        assert result[1].event.subject == TestReadEvents.LOGGED_IN_SUBJECT
        assert result[1].event.type == logged_in_type('janeDoe')
        assert result[2].event.source == TEST_SOURCE
        assert result[2].event.subject == TestReadEvents.REGISTERED_SUBJECT
        assert result[2].event.type == registered_type('johnDoe')
        assert result[3].event.source == TEST_SOURCE
        assert result[3].event.subject == TestReadEvents.LOGGED_IN_SUBJECT
        assert result[3].event.type == logged_in_type('johnDoe')
