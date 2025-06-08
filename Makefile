# Variables for reusable values
PACKAGE := eventsourcingdb
TEST_DIR := tests
PYTHON_DIRS := $(PACKAGE) $(TEST_DIR)

# Default target and help
.DEFAULT_GOAL := .PHONY
help:
	@echo "Available commands:"
	@echo "  qa       : Run analysis and tests"
	@echo "  analyze  : Run code analysis with ruff"
	@echo "  format   : Format code"
	@echo "  test     : Run tests"
	@echo "  coverage : Check test coverage"
	@echo "  lock     : Lock dependencies with uv"
	@echo "  clean    : Remove temporary files"
	@echo "  build    : Run QA and prepare build"

qa: analyze test

analyze:
	@uv add ruff --dev
	@echo "Running code analysis..."
	@uv run ruff check $(PYTHON_DIRS)

format:
	@uv add ruff --dev
	@echo "Formatting code..."
	@uv run ruff format $(PYTHON_DIRS)

lock:
	@echo "Updating dependency lock..."
	@uv run uv lock 

test:
	@uv add pytest --dev
	@echo "Running tests..."
	@uv run pytest --maxfail=1

coverage:
	@uv add pytest --dev
	@uv add pytest-cov --dev
	@echo "Checking test coverage..."
	@uv run pytest --cov=$(PACKAGE) --cov-report=term-missing $(TEST_DIR)

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
	@rm -rf build/ dist/ .coverage htmlcov/

build: qa clean
	@echo "Build prepared."

.PHONY: analyze build clean format lock qa test coverage help
