# Python Development Rules

## Project Management
- **uv**: Use `uv` for all project and dependency management
- **Dependencies**: Declare in `pyproject.toml`, install with `uv sync`
- **Virtual Environment**: Managed automatically by `uv`

## Code Quality
- **Linting**: Use `ruff` for linting and auto-fixing
- **Formatting**: Use `ruff format` for code formatting
- **Testing**: Use `pytest` for all tests
- **Type Hints**: Use type hints where beneficial for readability

## Development Workflow
- **Pre-commit**: Code must pass linting and testing before being committed
- **Commands**:
  - `uv run ruff check --fix .` - Fix linting issues
  - `uv run ruff format .` - Format code
  - `uv run pytest` - Run tests
- **CI/CD**: All checks must pass in automated pipelines

## Code Standards
- **Line Length**: 120 characters (configured in pyproject.toml)
- **Import Sorting**: Handled by ruff with isort integration
- **Docstrings**: Use for public APIs and complex functions
- **Error Handling**: Use appropriate exception types, avoid bare except clauses
