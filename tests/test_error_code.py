import re

from eventsourcingdb import ErrorCode

from .shared.server_error_slugs import SERVER_ERROR_SLUGS

SLUG_PATTERN = re.compile(r'^\s*Slug\w+\s*=\s*"([a-z-]+)"\s*$', re.MULTILINE)


class TestErrorCode:
    @staticmethod
    def test_has_a_constant_for_every_code_the_server_lists_and_no_other() -> None:
        slugs = SLUG_PATTERN.findall(SERVER_ERROR_SLUGS)

        assert len(slugs) == len(SERVER_ERROR_SLUGS.strip().splitlines()) - 2
        assert {code.name: code.value for code in ErrorCode} == {
            slug.upper().replace('-', '_'): f'https://docs.eventsourcingdb.io/errors/{slug}'
            for slug in slugs
        }

    @staticmethod
    def test_compares_equal_to_the_code_as_the_server_sends_it() -> None:
        code = 'https://docs.eventsourcingdb.io/errors/precondition-violated'

        assert code == ErrorCode.PRECONDITION_VIOLATED
        assert ErrorCode(code) is ErrorCode.PRECONDITION_VIOLATED
        assert str(ErrorCode.PRECONDITION_VIOLATED) == code
