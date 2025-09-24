.PHONY: help test test-cov lint lint-fix typecheck check clean install dev

# Default target
help:
	@echo "Available commands:"
	@echo "  make test       - Run tests with pytest"
	@echo "  make lint       - Run all linting checks (ruff check, format check, mypy)"
	@echo "  make lint-fix   - Fix all linting issues (ruff check --fix, format, mypy)"
	@echo "  make typecheck  - Run mypy type checking only"
	@echo "  make check      - Run all checks (lint + test)"
	@echo "  make clean      - Clean up temporary files"

# Run tests
test:
	uv run pytest --cov=libertyjog --cov-report=term-missing


# Run all linting checks (check only, no fixes)
lint:
	@echo "Running ruff check..."
	uv run ruff check .
	@echo "Checking code formatting..."
	uv run ruff format --check .
	@echo "Running mypy type checking..."
	uv run mypy src/libertyjog

# Fix all linting issues
lint-fix:
	@echo "Running ruff check with auto-fix..."
	uv run ruff check --fix .
	@echo "Formatting code..."
	uv run ruff format .
	@echo "Running mypy type checking..."
	uv run mypy src/libertyjog

# Run type checking only
typecheck:
	uv run mypy src/libertyjog

# Clean up temporary files
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -name ".coverage" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +