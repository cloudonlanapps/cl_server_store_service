# Store Service - Internal Documentation

This document contains development-related information for contributors working on the store service.

## Package Structure

```
services/store/
├── src/store/                # Main application package
│   ├── __init__.py           # FastAPI app with lifespan management
│   ├── main.py               # CLI entry point (store command)
│   ├── models.py             # SQLAlchemy models (Entity, ServiceConfig)
│   ├── schemas.py            # Pydantic schemas
│   ├── routes.py             # API endpoints
│   ├── service.py            # Business logic
│   ├── auth.py               # JWT authentication
│   ├── database.py           # Database configuration
│   ├── config_service.py     # Runtime configuration service
│   ├── capability_manager.py # Worker capability discovery (MQTT)
│   ├── entity_storage.py     # Media entity storage service
│   └── versioning.py         # SQLAlchemy-Continuum setup
├── tests/                    # Test suite
│   ├── conftest.py           # Pytest fixtures
│   ├── test_entity_*.py      # Entity management tests
│   ├── test_job_*.py         # Job management tests
│   ├── test_plugin_*.py      # Plugin tests
│   ├── test_authentication.py # Auth tests
│   ├── README.md             # Test documentation
│   └── PLUGINS.md            # Plugin testing guide
├── alembic/                  # Database migrations
│   ├── versions/             # Migration scripts
│   └── env.py                # Alembic configuration
├── pyproject.toml            # Package configuration
├── README.md                 # User documentation
└── INTERNALS.md              # This file
```

**Key Design:**
- Uses shared models from `cl-server-shared` (Job, QueueEntry)
- Local models: Entity (media) and ServiceConfig (runtime settings)
- SQLite with WAL mode for concurrent access
- Optional JWT authentication with ES256
- SQLAlchemy-Continuum for entity versioning
- MQTT-based worker capability discovery
- Alembic for database migrations

## Development

### Running Tests

See [tests/README.md](tests/README.md) for detailed information on running tests, coverage options, and test structure.

**Quick commands:**
```bash
# Run all tests (coverage automatic: HTML + terminal reports, 90% required)
uv run pytest

# Run specific test file
uv run pytest tests/test_entity_crud.py -v

# Skip coverage for quick testing
uv run pytest --no-cov
```

**Coverage:** Automatically enabled via `pyproject.toml` - generates `htmlcov/` directory + terminal report, requires ≥90%

### Database Migrations

```bash
# Create a new migration
uv run alembic revision --autogenerate -m "Add new feature"

# Apply migrations
uv run alembic upgrade head

# Rollback one migration
uv run alembic downgrade -1

# Check current version
uv run alembic current
```

### Code Quality

```bash
# Format code
uv run ruff format src/

# Lint code
uv run ruff check src/

# Fix linting issues
uv run ruff check --fix src/
```

### Development Workflow

1. **Make changes** to code in `src/store/`
2. **Run tests** to ensure everything works: `uv run pytest`
3. **Create migration** if models changed: `uv run alembic revision --autogenerate -m "description"`
4. **Test the server** with auto-reload: `uv run store --reload --no-auth`
5. **Commit** your changes

### Adding Dependencies

```bash
# Add a new dependency
uv add package-name

# Add a development dependency
uv add --dev package-name

# Update all dependencies
uv sync --upgrade
```

## Architecture Notes

### Database Design

**Multi-tenant Database Strategy:**
- Store and worker services share the same database (`media_store.db`)
- Auth service uses separate database (`user_auth.db`)
- WAL mode enabled for concurrent read/write access
- Shared models (Job, QueueEntry) imported from `cl-server-shared`

**Local Models:**
- `Entity` - Media files with metadata, versioning, and soft deletes
- `ServiceConfig` - Runtime configuration with caching

### Authentication System

**Flexible Authentication Modes:**
- `AUTH_DISABLED=true` - No authentication required
- `READ_AUTH_ENABLED=false` - Write operations require token, reads are public
- `READ_AUTH_ENABLED=true` - All operations require token

**Permission Types:**
- `media_store_read` - Read media entities
- `media_store_write` - Write/modify media entities
- `ai_inference_support` - Create/manage compute jobs
- `admin` - Administrative operations

**Token Verification:**
- Public key fetched from auth service at `PUBLIC_KEY_PATH`
- ES256 (ECDSA with SHA-256) signature verification
- Stateless JWT tokens with expiration

### Worker Capability Discovery

**MQTT-Based Discovery:**
- Workers publish capabilities to MQTT broker
- Store service subscribes to capability announcements
- `CapabilityManager` maintains real-time worker registry
- Used for job routing and supported task type queries

**Configuration:**
- `MQTT_BROKER` - Broker hostname (default: localhost)
- `MQTT_PORT` - Broker port (default: 1883)
- `MQTT_TOPIC` - Topic for capability announcements

### Versioning with SQLAlchemy-Continuum

**Entity History Tracking:**
- Automatic version creation on entity changes
- `versioning.py` must be imported before models
- Versions stored in `entity_version` table
- Track who changed what and when

**Critical Import Order:**
```python
# MUST import versioning BEFORE models
from . import versioning  # Sets up continuum
from .models import Entity  # Now versioning is active
```

### Compute Plugin Integration

**cl_ml_tools Integration:**
- Plugins register via `create_master_router()`
- Mounted at `/compute` prefix
- Automatic parameter validation
- File upload handling
- Job lifecycle management

**Plugin Requirements:**
- Each plugin provides its own route (e.g., `/compute/jobs/image_resize`)
- Parameters validated by plugin-specific Pydantic models
- See [tests/PLUGINS.md](tests/PLUGINS.md) for testing guide

## Service Integration

### With Auth Service
- Store service runs on port 8001
- Fetches public key from auth service for JWT verification
- Shares user permissions for authorization
- Independent operation possible with `AUTH_DISABLED=true`

### With Worker Services
- Workers share same database for job claiming
- MQTT for capability announcements
- Store creates jobs, workers claim and process them
- Status updates via shared database

### File Storage

**Entity Storage:**
- Media files stored in `MEDIA_STORAGE_DIR` (default: `$CL_SERVER_DIR/media`)
- MD5-based duplicate detection
- Original filename preservation
- Metadata extraction (dimensions, duration, MIME type)

**Compute Storage:**
- Job files in `COMPUTE_STORAGE_DIR` (default: `$CL_SERVER_DIR/compute`)
- Separate input/output directories per job
- Automatic cleanup on job deletion

## Testing Strategy

Tests are organized by functionality:
- `test_entity_*.py` - Media entity management
- `test_job_*.py` - Job orchestration
- `test_plugin_*.py` - Compute plugins
- `test_authentication.py` - Authentication flows
- `test_*_permissions.py` - Authorization
- `test_integration_*.py` - End-to-end workflows
- `test_versioning.py` - Entity history tracking
- `test_duplicate_detection.py` - MD5 deduplication

All tests use in-memory SQLite databases and isolated test clients.

For plugin testing, see [tests/PLUGINS.md](tests/PLUGINS.md).

## Future Enhancements

### Media Management
- Support for additional media types (audio, documents)
- Thumbnail generation and caching
- Advanced search with full-text indexing
- Bulk operations (move, delete, tag)

### Job Management
- Job scheduling with cron-like syntax
- Job dependencies and workflows
- Automatic retry with exponential backoff
- Job result caching

### Performance
- Redis caching for frequently accessed entities
- Database connection pooling optimization
- Lazy loading for large collections
- Pagination improvements

### Security
- Rate limiting for API endpoints
- File upload size limits
- Content-type validation
- Malware scanning integration

### Monitoring
- Prometheus metrics export
- Job queue depth monitoring
- Worker health tracking
- API endpoint latency tracking

### Storage
- S3-compatible object storage support
- Storage quota management
- Automatic archival of old media
- Storage cost optimization

## Contributing

When contributing to this service:
1. Maintain 90%+ test coverage
2. Run linter and formatter before committing
3. Create migrations for any model changes
4. Update API documentation in README.md for user-facing changes
5. Add entries to Future Enhancements section for planned features
6. Follow the plugin testing guide for compute plugins
