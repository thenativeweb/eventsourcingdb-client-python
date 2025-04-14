analyze:
	@poetry run pylint eventsourcingdb tests

build: qa clean

clean:

format:
	@poetry run autopep8 --in-place --aggressive --max-line-length=100 --recursive eventsourcingdb tests

lock:
	@poetry lock

qa: analyze test

test:
	@poetry run pytest --maxfail=1

.PHONY: analyze build clean format lock qa test
