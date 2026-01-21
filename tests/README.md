# Tests for CL Server Store Service

This directory contains the test suite for the store microservice. The tests cover media management, job orchestration, authentication, permissions, and integration workflows using `pytest`.

## Overview & Structure

The test suite is organized into two categories:

- **Unit tests** (`test_*.py`) — Test individual components with in-memory SQLite databases and mocked dependencies
- **Integration tests** (`test_integration_*.py`) — Test end-to-end workflows with full service integration

## Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- Dependencies installed via `uv sync`

**Note:** With uv, you don't need to manually create or activate virtual environments. Use `uv run` to execute commands in the automatically managed environment.

## Running Tests

### Run All Tests

To run the entire test suite with coverage:

```bash
uv run pytest
```

**Coverage requirement:** 90% (configured in `pyproject.toml`)

### Run Specific Test Files

To run tests from a specific file:

```bash
uv run pytest tests/test_entity_crud.py -v
uv run pytest tests/test_job_crud.py -v
uv run pytest tests/test_authentication.py -v
uv run pytest tests/test_plugin_image_resize.py -v
```

### Run Individual Tests

To run a specific test function:

```bash
uv run pytest tests/test_entity_crud.py::test_create_entity -v
uv run pytest tests/test_authentication.py::test_login_success -v
```

### Coverage Options

**Default behavior:** Coverage is automatically collected with HTML + terminal reports and requires ≥90% coverage.

```bash
# Run tests with coverage (generates htmlcov/ directory + terminal report)
uv run pytest

# Skip coverage for quick testing
uv run pytest --no-cov

# Override coverage threshold (e.g., for debugging)
uv run pytest --cov-fail-under=0
```

Coverage reports are saved to `htmlcov/index.html` - open this file in a browser to view detailed coverage.

## Test Structure

The tests are organized into the following categories:

| File Pattern | Description |
|--------------|-------------|
| `test_entity_*.py` | Media entity management tests (CRUD, validation, versioning) |
| `test_job_*.py` | Job management and orchestration tests |
| `test_plugin_*.py` | Compute plugin tests (image processing, etc.) |
| `test_authentication.py` | Authentication and token validation tests |
| `test_*_permissions.py` | Permission and authorization tests |
| `test_integration_*.py` | End-to-end integration tests |
| `test_file_*.py` | File upload and storage tests |
| `conftest.py` | Pytest fixtures for database sessions, test clients, and mock data |

### Key Test Files

| File | Description |
|------|-------------|
| `conftest.py` | Shared fixtures (DB sessions, clients, mock data) |
| `test_entity_crud.py` | Media entity CRUD operations |
| `test_job_crud.py` | Job CRUD operations |
| `test_authentication.py` | Authentication flows and token validation |
| `test_plugin_image_resize.py` | Image resize plugin tests |
| `test_plugin_image_conversion.py` | Image conversion plugin tests |
| `test_unified_permissions.py` | Permission-based access control |
| `test_versioning.py` | Entity versioning with SQLAlchemy-Continuum |
| `test_duplicate_detection.py` | MD5-based duplicate detection |

## Plugin Testing

For detailed information on creating and testing compute plugins, see [../../docs/store-plugins-testing.md](../../docs/store-plugins-testing.md).

Quick reference:
- Use `test_plugin_template.py.template` as a starting point
- Follow the checklist in store-plugins-testing.md for comprehensive coverage
- Test both functional behavior and authentication/authorization

## Configuration

The test configuration is defined in `pyproject.toml` under `[tool.pytest.ini_options]`:
- **Test Paths**: `tests`
- **Coverage**: Automatically enabled with HTML + terminal reports
- **Coverage Threshold**: 90% minimum (tests fail if below)
- **Asyncio Mode**: Auto-detection for async tests

## Quick Reference

For a quick command reference, see [QUICK.md](QUICK.md)
