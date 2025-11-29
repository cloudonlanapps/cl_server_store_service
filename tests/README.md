# Tests for CL Server Store Service

This directory contains the test suite for the media store microservice. The tests are written using `pytest` and cover file upload, metadata extraction, versioning, authentication, duplicate detection, and CRUD operations.

## Prerequisites

Ensure you have Python 3.9+ installed.

### Setting up the Environment

If you don't have a virtual environment set up yet, follow these steps:

1.  **Create a virtual environment:**
    ```bash
    python3 -m venv venv
    ```

2.  **Activate the virtual environment:**
    - On macOS/Linux:
        ```bash
        source venv/bin/activate
        ```
    - On Windows:
        ```bash
        .\venv\Scripts\activate
        ```

3.  **Install dependencies and the package in editable mode:**
    This ensures that the `src` package is available to the tests.
    ```bash
    pip install -e .
    ```
    This command installs the dependencies listed in `pyproject.toml` (including `pytest`, `httpx`, `python-jose`, etc.) and installs the current package in editable mode.

## Running Tests

Make sure your virtual environment is activated.

### Run All Tests

To run the entire test suite:

```bash
pytest
```

### Run Specific Test Files

To run tests from a specific file:

```bash
pytest tests/test_authentication.py
pytest tests/test_entity_crud.py
pytest tests/test_pagination.py
pytest tests/test_versioning.py
pytest tests/test_file_upload.py
pytest tests/test_duplicate_detection.py
pytest tests/test_admin_endpoints.py
pytest tests/test_health_check.py
```

### Run Individual Tests

To run a specific test function:

```bash
pytest tests/test_entity_crud.py::TestEntityCRUD::test_create_collection
pytest tests/test_authentication.py::TestJWTValidation::test_valid_token_is_decoded
```

### Run Tests with Verbose Output

For more detailed output:

```bash
pytest -v
```

### Run Tests with Coverage Report

To see test coverage:

```bash
pytest --cov=src --cov-report=html
```

## Test Structure

The tests are organized into the following files:

| File | Description |
|------|-------------|
| `tests/conftest.py` | Pytest fixtures for database sessions, test client, JWT token generation, and test media files. Provides both `client` (auth bypassed) and `auth_client` (full auth) fixtures. |
| `tests/test_authentication.py` | Tests for authentication logic, JWT token validation (ES256), permission checks, and authentication modes (AUTH_DISABLED, READ_AUTH_ENABLED). |
| `tests/test_admin_endpoints.py` | Tests for admin configuration endpoints (GET/PUT /admin/config) with JWT authentication and permission validation. |
| `tests/test_entity_crud.py` | Tests for entity CRUD operations (Create, Read, Update, Delete), soft delete/restore, and hierarchy management. |
| `tests/test_pagination.py` | Tests for pagination functionality with versioning support, including edge cases and metadata accuracy. |
| `tests/test_versioning.py` | Tests for entity versioning using SQLAlchemy-Continuum, including version creation, querying, and history tracking. |
| `tests/test_file_upload.py` | Tests for file upload functionality with metadata extraction (MD5, dimensions, MIME type, EXIF data). |
| `tests/test_file_storage.py` | Tests for file storage organization (YYYY/MM/DD structure), MD5-based naming, and file deletion on updates. |
| `tests/test_duplicate_detection.py` | Tests for MD5-based duplicate detection, ensuring duplicate files return existing entities. |
| `tests/test_comprehensive_metadata.py` | Comprehensive metadata extraction tests for all test images, including timestamps and file paths. |
| `tests/test_entity_validation.py` | Tests for entity validation rules (collections vs non-collections, required fields, immutable fields). |
| `tests/test_put_endpoint.py` | Tests for PUT endpoint file replacement, metadata extraction, and update behavior. |
| `tests/test_user_tracking.py` | Tests for user tracking fields (added_by, updated_by) across create, update, and version history. |
| `tests/test_runtime_config.py` | Tests for runtime configuration API, ConfigService caching, and read authentication behavior. |
| `tests/test_health_check.py` | Tests for health check endpoint (GET /) returning service status and version. |
| `tests/test_config.py` | Test configuration module providing centralized paths and test file loading from test_files.txt. |
| `tests/test_media_files.py` | Helper module for loading test media files from the images directory. |

## Test Configuration

The test configuration is defined in `pyproject.toml` under `[tool.pytest.ini_options]`:
- **Test Paths**: `tests`
- **Python Files**: `test_*.py`
- **Addopts**: `-v --tb=short` (Verbose output, short traceback)

### Test Fixtures

Key fixtures available in `conftest.py`:

- **`client`**: TestClient with authentication bypassed (for testing business logic)
- **`auth_client`**: TestClient with full authentication (for testing auth flows)
- **`test_engine`**: In-memory SQLite database engine with versioning support
- **`test_db_session`**: Database session for direct database operations
- **`clean_media_dir`**: Temporary media directory cleaned before/after each test
- **`sample_image`**: Single test image file path
- **`sample_images`**: Multiple test image file paths (up to 30)
- **`jwt_token_generator`**: Helper for generating JWT tokens with configurable claims
- **`admin_token`**: Valid admin JWT token
- **`write_token`**: Valid write-only JWT token
- **`read_token`**: Valid read-only JWT token
- **`key_pair`**: ES256 key pair for JWT signing/validation

### Test Images

Test images are loaded from `test_files.txt`, which contains relative paths to image files. The test suite expects images to be available in the `../images` directory (sibling to the store service directory).

If test images are not available, tests requiring images will be skipped with an appropriate message.

## Coverage Areas

The test suite provides comprehensive coverage for:

✅ **Authentication & Authorization**
- JWT token validation with ES256 algorithm
- Permission-based access control (read, write, admin)
- Authentication modes and configuration

✅ **Entity Management**
- CRUD operations for entities and collections
- Soft delete and restore functionality
- Hierarchy management (parent-child relationships)

✅ **File Handling**
- File upload with automatic metadata extraction
- File storage organization (YYYY/MM/DD structure)
- MD5-based duplicate detection
- File replacement on updates

✅ **Versioning**
- Automatic version creation on updates
- Version history tracking
- Querying specific versions

✅ **Metadata Extraction**
- Image dimensions, file size, MIME type
- EXIF data extraction (create date, camera info)
- MD5 hash calculation

✅ **Pagination**
- Page-based navigation
- Custom page sizes
- Pagination with versioning support

✅ **User Tracking**
- added_by and updated_by fields
- User tracking across versions

✅ **Configuration**
- Runtime configuration management
- Read authentication toggle
- Configuration persistence

## Known Limitations

⚠️ **Minor Issues**:
- `test_runtime_config.py` contains placeholder tests for JWT user ID validation (marked with `pass`)
- Some validation tests use broad error code expectations `[400, 422, 500]` instead of specific codes
- Limited coverage for video file handling (tests are primarily image-focused)
- No tests for concurrent access or race conditions

## Notes

- Tests use an in-memory SQLite database for isolation
- Each test gets a fresh database and clean media directory
- Test artifacts are stored in `../test_artifacts/cl_server` (outside the project directory)
- The `CL_SERVER_DIR` environment variable is overridden during tests to prevent contamination of production data
