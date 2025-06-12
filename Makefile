PACKAGE := eventsourcingdb
TEST_DIR := tests
PYTHON_DIRS := $(PACKAGE) $(TEST_DIR)

qa: analyze typecheck security test

analyze:
	@echo "Running code analysis..."
	@uv run ruff check $(PYTHON_DIRS)

build: qa clean
	@echo "Build prepared."

coverage:
	@echo "Checking test coverage..."
	@uv run pytest --cov=$(PACKAGE) --cov-report=term-missing $(TEST_DIR)

format:
	@echo "Formatting code..."
	@uv run ruff format $(PYTHON_DIRS)

lock:
	@echo "Updating dependency lock..."
	@uv run uv lock

security:
	@echo "Running security checks..."
	@uv run bandit -r $(PACKAGE) -c pyproject.toml

test:
	@echo "Running tests..."
	@uv run pytest --maxfail=1

typecheck:
	@uv add pyright --dev
	@echo "Running type checking..."
	@uv run pyright $(PACKAGE)

.PHONY: analyze build clean coverage format help lock qa security test typecheck
