qa: analyze test

analyze:
	@poetry run pylint eventsourcingdb tests

format:
	@poetry run autopep8 --in-place --aggressive --max-line-length=100 --recursive eventsourcingdb tests
	
lock:
	@poetry lock 

test:
	@poetry run pytest --maxfail=1

clean:

build: qa clean

.PHONY: analyze build clean format lock qa test
