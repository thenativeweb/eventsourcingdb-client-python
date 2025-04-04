qa: analyze test

analyze:
	@poetry run pylint eventsourcingdb tests

fix:
	@poetry run autopep8 --in-place --aggressive --max-line-length=100 --recursive eventsourcingdb_client_python tests
	
test:
	@poetry run pytest --maxfail=1

clean:

build: qa clean

.PHONY: fix analyze build clean qa test
