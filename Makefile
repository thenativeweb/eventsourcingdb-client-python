PACKAGE := eventsourcingdb
TEST_DIR := tests
PYTHON_DIRS := $(PACKAGE) $(TEST_DIR)

qa: analyze typecheck security test 

analyze:
	@echo "Running code analysis..."
	@uv run ruff check $(PYTHON_DIRS)

build: qa clean
	@echo "Build prepared."

clean:
	@echo "Cleaning up..."
	@find . -type d -name __pycache__ -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name "*.pyo" -delete
	@find . -type f -name "*.pyd" -delete
	@find . -type f -name ".coverage" -delete
	@find . -type d -name "*.egg-info" -exec rm -rf {} +
	@find . -type d -name "*.egg" -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@find . -type d -name ".mypy_cache" -exec rm -rf {} +
	@find . -type d -name ".pyright" -exec rm -rf {} +
	@find . -type d -name ".ruff_cache" -exec rm -rf {} +
	@rm -rf build/ dist/ .coverage htmlcov/ .venv/

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

.PHONY: analyze build coverage format help lock qa security test typecheck clean
