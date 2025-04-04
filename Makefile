qa: analyze test

analyze:
	@poetry run pylint eventsourcingdb tests

test:
	@poetry run pytest --maxfail=1

clean:

build: qa clean

.PHONY: analyze build clean qa test
