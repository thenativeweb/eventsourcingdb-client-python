qa: analyze test

analyze:
	@poetry run pylint eventsourcingdb_client_python tests

test:
	@poetry run pytest

clean:

build: qa clean

.PHONY: analyze build clean qa test
