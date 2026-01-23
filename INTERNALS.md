# Store Service - Internal Documentation

This document contains development-related information for contributors working on the store service.

## Package Structure

```
services/store/
├── src/store/                # Main application package
│   ├── __init__.py           # Package initialization
│   ├── main.py               # CLI entry point (store command)
│   ├── m_insight_worker.py   # CLI entry point (m-insight-worker command)
│   │
│   ├── common/               # Shared infrastructure
│   │   ├── __init__.py
│   │   ├── auth.py           # JWT authentication & verification
│   │   ├── config.py         # Base configuration classes
│   │   ├── database.py       # Database session management
│   │   ├── models.py         # SQLAlchemy models (Entity, Face, ImageIntelligence, etc.)
│   │   ├── schemas.py        # Shared Pydantic schemas
│   │   ├── storage.py        # File storage service abstraction
│   │   ├── utils.py          # Shared utility functions
│   │   └── versioning.py     # SQLAlchemy-Continuum setup (CRITICAL: import before models)
│   │
│   ├── store/                # Media store service
│   │   ├── __init__.py
│   │   ├── config.py         # Store-specific configuration
│   │   ├── config_service.py # Runtime configuration management
│   │   ├── dependencies.py   # FastAPI dependency injection
│   │   ├── media_metadata.py # ExifTool & ffprobe metadata extraction
│   │   ├── monitor.py        # Monitoring and health check utilities
│   │   ├── routes.py         # Entity management API endpoints
│   │   ├── service.py        # Entity CRUD business logic
│   │   └── store.py          # FastAPI app creation with lifespan management
│   │
│   └── m_insight/            # Media insight (mInsight) service
│       ├── __init__.py
│       ├── broadcaster.py    # MQTT status broadcasting
│       ├── config.py         # mInsight-specific configuration
│       ├── dependencies.py   # FastAPI dependency injection
│       ├── job_callbacks.py  # Job completion handlers (store results in DB/Qdrant)
│       ├── job_service.py    # Job creation & tracking (face detection, embeddings)
│       ├── media_insight.py  # Core reconciliation processor
│       ├── retrieval_service.py # Similarity search via Qdrant
│       ├── routes.py         # Intelligence API endpoints (search, retrieve)
│       ├── schemas.py        # mInsight-specific Pydantic schemas
│       └── vector_stores.py  # Qdrant singleton for CLIP/DINO/face embeddings
│
├── tests/                    # Test suite
│   ├── conftest.py           # Pytest fixtures (sessions, clients, tokens)
│   ├── test_cascade_deletion.py    # Cascade deletion verification
│   ├── test_config.py        # Configuration management tests
│   ├── test_m_insight_mqtt.py # MQTT integration tests
│   ├── test_m_insight_worker.py # Worker reconciliation tests
│   ├── test_media_files.py   # Media file handling tests
│   ├── test_mqtt_broadcast.py # Broadcasting functionality tests
│   ├── test_store/
│   │   └── test_integration/ # Store service integration tests
│   │       ├── test_entity_crud.py
│   │       ├── test_authentication.py
│   │       ├── test_file_upload.py
│   │       └── ... (12+ integration test files)
│   ├── README.md             # Comprehensive test documentation
│   └── QUICK.md              # Quick test command reference
│
├── alembic/                  # Database migrations (Alembic)
│   ├── versions/             # Migration scripts
│   │   ├── a8181ccb4efa_initial_schema_from_current_models.py
│   │   ├── 0e06b756fe80_add_m_insight_tables.py
│   │   ├── 00268ae3f7cc_add_image_path_and_version_to_.py
│   │   └── 6d29391ba950_consolidate_models_and_add_job_tracking.py
│   ├── env.py                # Alembic configuration
│   ├── script.py.mako        # Migration template
│   └── README                # Alembic documentation
│
├── pyproject.toml            # Package configuration (dependencies, scripts, pytest config)
├── README.md                 # User-facing documentation
├── INTERNALS.md              # This file (developer documentation)
├── REVIEW.md                 # Comprehensive code review with 86+ issues
└── CLAUDE.md                 # Claude Code guidance documentation
```

**Key Design Decisions:**

**Service Architecture:**
- **Three-layer structure:** Common infrastructure, Store service, mInsight service
- **Shared database:** Both store and mInsight worker use same SQLite DB (`media_store.db`)
- **Separate executables:** `store` command runs FastAPI server, `m-insight-worker` runs background processor
- **Event-driven:** MQTT optional for job status broadcasting and worker coordination

**Data Models:**
- **Entity** - Core media entity model with versioning (common/models.py)
- **ImageIntelligence** - Processing status & job tracking for each entity
- **Face** - Detected faces with bounding boxes, embeddings, person links
- **KnownPerson** - Person clustering via face embeddings
- **EntityJob** - Job lifecycle tracking (queued → processing → completed/failed)

**Technology Stack:**
- **Database:** SQLite with WAL mode for concurrent read/write access
- **ORM:** SQLAlchemy with SQLAlchemy-Continuum for versioning
- **API:** FastAPI with Pydantic for validation
- **Authentication:** Optional JWT with ES256 (ECDSA) signatures
- **Migrations:** Alembic for schema evolution
- **Vector Store:** Qdrant for CLIP/DINO/face embeddings
- **Job Communication:** MQTT (optional) for broadcasting

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

# Type checking
uv run basedpyright
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

### Service Separation: Store vs mInsight

This package contains two distinct but integrated services:

**1. Store Service (`store` command)**
- **Purpose:** RESTful API for media entity management
- **Responsibilities:**
  - Entity CRUD operations (create, read, update, delete)
  - File storage and metadata extraction (ExifTool, ffprobe)
  - Entity versioning with SQLAlchemy-Continuum
  - Duplicate detection via MD5 hashing
  - Runtime configuration management
- **Entry Point:** `src/store/main.py` → runs FastAPI server
- **API Routes:** `src/store/store/routes.py`
- **Database:** Writes to `media_store.db`

**2. mInsight Service (`m-insight-worker` command)**
- **Purpose:** Background processor for ML intelligence on media entities
- **Responsibilities:**
  - Entity reconciliation (detect new/changed entities since last run)
  - Job creation for face detection, CLIP embeddings, DINO embeddings
  - Job completion handling (store results in database + Qdrant)
  - Face clustering and person recognition
  - Similarity search via vector embeddings
- **Entry Point:** `src/store/m_insight_worker.py` → runs reconciliation loop
- **API Routes:** `src/store/m_insight/routes.py` (search/retrieval endpoints)
- **Database:** Reads/writes to `media_store.db` (shared with store)
- **Vector Store:** Qdrant for embeddings storage

**Integration Pattern:**
1. User uploads media via Store API → Entity created
2. mInsight worker detects new Entity → creates jobs
3. Compute workers process jobs → return results
4. mInsight job callbacks → store Face records, embeddings in Qdrant
5. User queries via mInsight API → similarity search across embeddings

**Communication:**
- **Database:** Primary communication channel (shared SQLite DB)
- **MQTT (optional):** Real-time job status broadcasting
- **HTTP:** mInsight can call Store API for entity operations

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
- `--no-auth` CLI flag - No authentication required
- Default mode - Write operations require token, reads are public
- `READ_AUTH_ENABLED=true` configuration - All operations require token

**Permission Types:**
- `media_store_read` - Read media entities
- `media_store_write` - Write/modify media entities
- `ai_inference_support` - Create/manage compute jobs
- `admin` - Administrative operations

**Token Verification:**
- Public key from auth service used for ES256 signature verification
- Stateless JWT tokens with expiration

### Worker Capability Discovery

**MQTT-Based Discovery:**
- Workers publish capabilities to MQTT broker
- Store service subscribes to capability announcements
- `CapabilityManager` maintains real-time worker registry
- Used for job routing and supported task type queries

**Configuration via CLI:**
- `--mqtt-server` - Broker hostname (default: localhost)
- `--mqtt-port` - Broker port (enables MQTT when set)

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
- See [../../docs/store-plugins-testing.md](../../docs/store-plugins-testing.md) for testing guide

### File Storage

**Entity Storage:**
- Media files stored in `$CL_SERVER_DIR/media`
- MD5-based duplicate detection
- Original filename preservation
- Metadata extraction (dimensions, duration, MIME type)

**Compute Storage:**
- Job files in `$CL_SERVER_DIR/compute`
- Separate input/output directories per job
- Automatic cleanup on job deletion

**Note:** For system-wide architecture and inter-service communication, see [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) in the repository root.

### mInsight Processing Pipeline

**Entity Reconciliation Flow:**

1. **Worker Polls for New Entities:**
   - Queries `EntitySyncState` to find last processed version
   - Gets all entities created/modified since last version
   - Filters for image entities (non-collections with media files)

2. **Job Creation (`job_service.py`):**
   - For each new image entity:
     - Create `ImageIntelligence` record with status="queued"
     - Submit face detection job → `face_detection_job_id`
     - Submit CLIP embedding job → `clip_job_id`
     - Submit DINO embedding job → `dino_job_id`
   - Jobs tracked in `EntityJob` table (status: queued → in_progress → completed/failed)

3. **Job Processing (External Compute Workers):**
   - Workers pull jobs from compute service queue
   - Process images (face detection, embedding generation)
   - Return results to compute service

4. **Job Completion Callbacks (`job_callbacks.py`):**
   - **Face Detection Callback:**
     - Create `Face` records in database
     - Save cropped face images to disk
     - Submit face embedding jobs for each detected face
     - Update `ImageIntelligence.face_detection_job_id`

   - **CLIP Embedding Callback:**
     - Store embedding vector in Qdrant (collection: `clip_embeddings`)
     - Update `ImageIntelligence.clip_job_id`

   - **DINO Embedding Callback:**
     - Store embedding vector in Qdrant (collection: for duplicate detection)
     - Update `ImageIntelligence.dino_job_id`

   - **Face Embedding Callback:**
     - Store face embedding in Qdrant (`face_embeddings` collection)
     - Perform similarity search to find matching faces
     - Link face to `KnownPerson` or create new person
     - Create `FaceMatch` records for similar faces

5. **Status Updates:**
   - Update `ImageIntelligence.status` to "completed" when all jobs done
   - Update `EntitySyncState.last_version` to latest processed version
   - Optional: Broadcast status via MQTT

**Vector Store Integration:**

**Qdrant Collections:**
- `clip_embeddings` - Image-level semantic embeddings for similarity search
- `dino_embeddings` - Image-level features for duplicate detection
- `face_embeddings` - Face-level embeddings for person recognition

**Retrieval Service (`retrieval_service.py`):**
- **Similarity Search:** Query Qdrant with image/text embedding → find similar images
- **Face Search:** Query face embeddings → find images of same person
- **Duplicate Detection:** Query DINO embeddings → find near-duplicate images

**Broadcaster Pattern (MQTT):**

**Purpose:** Optional real-time status updates for monitoring/debugging

**MInsightBroadcaster (`broadcaster.py`):**
- Publishes status messages to MQTT topic (e.g., `store/8001/items`)
- Message types:
  - `status_update` - Worker heartbeat (every 5 seconds)
  - `job_created` - New job submitted
  - `job_completed` - Job finished successfully
  - `job_failed` - Job failed with error
  - `entity_processed` - Entity reconciliation completed

**Configuration:**
- Enable with `--mqtt-port 1883` on both store and worker
- Broker defaults to localhost
- Topic configurable via `--mqtt-topic`

## Testing Strategy

See [tests/README.md](tests/README.md) for comprehensive testing documentation, including test organization, fixtures, and coverage requirements.

Tests are organized by functionality:

**Top-Level Tests:**
- `test_cascade_deletion.py` - Cascade deletion verification for related entities
- `test_config.py` - Configuration management and validation
- `test_m_insight_mqtt.py` - MQTT integration for mInsight broadcasting
- `test_m_insight_worker.py` - Worker reconciliation and job processing
- `test_media_files.py` - Media file handling and metadata
- `test_mqtt_broadcast.py` - MQTT broadcasting functionality

**Integration Tests (`test_store/test_integration/`):**
- `test_entity_crud.py` - Entity CRUD operations
- `test_authentication.py` - JWT authentication flows
- `test_file_upload.py` - File upload and storage
- `test_put_endpoint.py` - PUT endpoint validation
- `test_patch_endpoint.py` - PATCH endpoint validation
- `test_versioning.py` - SQLAlchemy-Continuum entity history
- `test_duplicate_detection.py` - MD5-based duplicate detection
- `test_pagination.py` - Pagination and page size validation
- `test_user_tracking.py` - User identity tracking
- `test_admin_endpoints.py` - Administrative operations
- `test_runtime_config.py` - Runtime configuration updates
- Plus additional integration tests

**Test Characteristics:**
- All tests use in-memory SQLite databases (`:memory:`)
- Isolated test clients with dependency override
- Fixtures provide JWT tokens with different permission levels
- Coverage requirement: ≥90% (enforced in pyproject.toml)
- HTML coverage reports generated in `htmlcov/`

For plugin testing, see [../../docs/store-plugins-testing.md](../../docs/store-plugins-testing.md).

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

---

## Plugin Testing Guide

This section explains how to create and test compute plugins for the CL Server Store Service.

### Test Categories

Each plugin test file contains the following test categories:

| Category | Description | Fixture Used |
|----------|-------------|--------------|
| **JobCreation** | Valid/invalid job creation | `client` |
| **JobRetrieval** | GET job by ID | `client` |
| **JobDeletion** | DELETE job | `client` |
| **JobLifecycle** | Create → Get → Delete | `client` |
| **Authentication** | 401 without token | `auth_client` |
| **Authorization** | 403 with wrong permission | `auth_client` |
| **TokenValidation** | Expired/invalid tokens | `auth_client` |

### Test Class Structure

Plugin tests follow a 7-class pattern. Only **TestJobCreation** varies by plugin; the other 6 classes are identical boilerplate:

| Class | Tests | Varies? | Purpose |
|-------|-------|---------|---------|
| TestJobCreation | 9-15 | ✅ Yes | Plugin-specific parameter validation |
| TestJobRetrieval | 2 | ❌ No | Standard GET operations |
| TestJobDeletion | 2 | ❌ No | Standard DELETE operations |
| TestJobLifecycle | 1 | ❌ No | Full workflow test |
| TestAuthentication | 4 | ❌ No | 401 error tests |
| TestAuthorization | 5 | ❌ No | 403 error tests |
| TestTokenValidation | 2 | ❌ No | Expired/invalid token tests |

**Implementation tip:** Copy boilerplate classes from template, customize only TestJobCreation for your plugin's parameters.

### Plugin Discovery Tests

Beyond testing plugin functionality, verify routes are properly registered:

```python
def test_plugin_route_exists(self, client):
    """Verify plugin route appears in OpenAPI schema."""
    response = client.get("/openapi.json")
    schema = response.json()

    # Check route exists
    assert "/compute/jobs/your_plugin" in schema["paths"]

    # Check HTTP method
    assert "post" in schema["paths"]["/compute/jobs/your_plugin"]

    # Check OpenAPI tags
    tags = schema["paths"]["/compute/jobs/your_plugin"]["post"]["tags"]
    assert "compute" in tags
```

**Purpose:** Ensures plugin routes are properly mounted and documented in API schema.

### Available Fixtures

#### `client` (conftest.py)

Test client with authentication **bypassed**. Use for functional tests.

```python
def test_something(self, client):
    response = client.post("/compute/jobs/image_resize", ...)
    assert response.status_code == 200
```

#### `auth_client` (conftest.py)

Test client with authentication **enabled**. Use for auth/permission tests.

```python
def test_requires_token(self, auth_client):
    response = auth_client.post("/compute/jobs/image_resize", ...)
    assert response.status_code == 401  # No token
```

#### Token Fixtures

| Fixture | Permission | Admin |
|---------|-----------|-------|
| `inference_token` | `ai_inference_support` | No |
| `inference_admin_token` | `ai_inference_support` | Yes |
| `write_token` | `media_store_write` | No |
| `read_token` | `media_store_read` | No |
| `admin_token` | `media_store_read`, `media_store_write` | Yes |

#### Fixture Usage Guidelines

**Use `client` for:**
- ✅ Functional tests (creation, retrieval, deletion, lifecycle)
- ✅ Parameter validation (422 errors)
- Auth is **bypassed** - automatic admin permissions

**Use `auth_client` for:**
- ✅ Authentication tests (401 - missing/invalid token)
- ✅ Authorization tests (403 - wrong permission)
- ✅ Token validation (expired, wrong signature)
- Auth is **enforced** - requires valid JWT

**Anti-pattern (DO NOT MIX):**
```python
# BAD: Mixing fixtures in same class confuses intent
class TestJobCreation:
    def test_valid(self, client):  # Auth bypassed
    def test_no_token(self, auth_client):  # Auth enforced ❌ WRONG CLASS

# GOOD: Separate classes by fixture type
class TestJobCreation:
    def test_valid(self, client):  # All use client

class TestAuthentication:
    def test_no_token(self, auth_client):  # All use auth_client
```

### HTTP Status Code Reference

| Code | Meaning | When Expected |
|------|---------|---------------|
| 200 | Success | Job created successfully |
| 204 | No Content | Job deleted successfully |
| 401 | Unauthorized | Missing, invalid, or expired token |
| 403 | Forbidden | Valid token, wrong permission |
| 404 | Not Found | Job ID doesn't exist |
| 422 | Validation Error | Invalid parameters (Pydantic) |
| 405 | Method Not Allowed | Route not registered |

**Permission requirements for job operations:**
- ✅ Required: `ai_inference_support` permission
- ❌ Insufficient: `media_store_write` (for media, not jobs)
- ❌ Insufficient: `media_store_read` (for media, not jobs)

### Creating Tests for a New Plugin

#### Step 1: Copy the Template

```bash
cp tests/test_plugin_template.py.template tests/test_plugin_<plugin_name>.py
```

#### Step 2: Replace Placeholders

Edit the new file and replace:

| Placeholder | Replace With | Example |
|-------------|-------------|---------|
| `{{PLUGIN_NAME}}` | Plugin name | `watermark` |
| `{{TASK_TYPE}}` | Task type string | `watermark` |
| `{{ENDPOINT}}` | API endpoint | `/compute/jobs/watermark` |

#### Step 3: Update Configuration

At the top of the file, update:

```python
PLUGIN_NAME = "watermark"
TASK_TYPE = "watermark"
ENDPOINT = "/compute/jobs/watermark"

VALID_JOB_DATA = {
    "priority": 5,
    "watermark_text": "Sample",
    "position": "bottom-right",
    "opacity": 0.5,
}

INVALID_JOB_DATA = {
    "priority": 15,  # Invalid
}
```

#### Step 4: Add Plugin-Specific Tests

Add tests for plugin-specific validation:

```python
def test_create_job_invalid_opacity(self, client, sample_image_file):
    """Test that creating a job with invalid opacity fails."""
    response = client.post(
        ENDPOINT,
        data={
            **VALID_JOB_DATA,
            "opacity": 1.5,  # Invalid: max is 1.0
        },
        files={"file": ("test.png", sample_image_file, "image/png")},
    )
    assert response.status_code == 422
```

#### Step 5: Modify Fixtures If Needed

If your plugin doesn't use images, update `sample_image_file`:

```python
@pytest.fixture
def sample_video_file(self):
    """Create a test video file."""
    # Return video bytes...
```

### Example: Image Resize Plugin Test

This example uses the `image_resize` plugin (matching the API example in README.md):

```python
"""Tests for image_resize plugin route."""

import io
import pytest
from PIL import Image

PLUGIN_NAME = "image_resize"
TASK_TYPE = "image_resize"
ENDPOINT = "/compute/jobs/image_resize"

VALID_JOB_DATA = {
    "priority": 5,
    "width": "800",
    "height": "600",
    "maintain_aspect_ratio": "false",
}


@pytest.fixture
def sample_image_file():
    img = Image.new('RGB', (100, 100), color='red')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes


class TestImageResizeJobCreation:
    def test_create_job_with_valid_data(self, client, sample_image_file):
        response = client.post(
            ENDPOINT,
            data=VALID_JOB_DATA,
            files={"file": ("test.png", sample_image_file, "image/png")},
        )
        assert response.status_code == 200

    def test_create_job_invalid_width_zero(self, client, sample_image_file):
        """Zero width should fail validation."""
        response = client.post(
            ENDPOINT,
            data={**VALID_JOB_DATA, "width": "0"},
            files={"file": ("test.png", sample_image_file, "image/png")},
        )
        assert response.status_code == 422

    def test_create_job_missing_file(self, client):
        """File upload is required."""
        response = client.post(ENDPOINT, data=VALID_JOB_DATA)
        assert response.status_code == 422


# ... continue with other test classes from template
```

### Test Coverage Checklist

For each plugin, ensure the following are tested:

#### Creation Tests
- [ ] Valid data → 200
- [ ] All optional parameters
- [ ] Each required parameter missing → 422
- [ ] Each parameter with invalid value → 422
- [ ] Missing file → 422
- [ ] Invalid priority → 422

#### Retrieval Tests
- [ ] Get by ID → 200
- [ ] Nonexistent ID → 404

#### Deletion Tests
- [ ] Delete by ID → 204
- [ ] Verify deletion → 404
- [ ] Nonexistent ID → 404

#### Lifecycle Tests
- [ ] Create → Get → Delete → Verify

#### Authentication Tests
- [ ] No token → 401
- [ ] Invalid token → 401
- [ ] Expired token → 401
- [ ] Wrong signature → 401

#### Authorization Tests
- [ ] Wrong permission → 403
- [ ] Correct permission → 200

### Plugin Test Template

A test template is available at:
- `tests/test_plugin_template.py.template` - Template for new plugin tests

### Skipped Legacy Tests

The following test files are skipped because they test the removed generic endpoint:

- `test_job_auth.py` - Tests `/compute/jobs/{task_type}` (removed)
- `test_job_crud.py` - Tests `/compute/jobs/{task_type}` (removed)

These endpoints have been replaced by plugin-specific routes (e.g., `/compute/jobs/image_resize`).

The functionality is now covered by the plugin-specific tests listed above.
