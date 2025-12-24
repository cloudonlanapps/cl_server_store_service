# CL Server Store Service

A FastAPI-based microservice for managing media entities and compute jobs. This service combines media entity management with metadata extraction, versioning, and duplicate detection, along with job management and task processing capabilities. It provides a comprehensive API for organizing and retrieving media files, managing compute jobs, and supporting the CL Server ecosystem.

**Server Port:** 8001 (default, configurable)
**Authentication Method:** JWT with ES256 (ECDSA) signature (optional)
**Package Manager:** uv
**Database:** SQLite with WAL mode

> **For Developers:** See [INTERNALS.md](INTERNALS.md) for package structure, development workflow, and contribution guidelines.

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- **ExifTool** - Required for EXIF metadata extraction
- **ffprobe** (part of FFmpeg) - Required for video duration extraction
- Set `CL_SERVER_DIR` environment variable

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install ExifTool and FFmpeg
# macOS:
brew install exiftool ffmpeg

# Linux (Debian/Ubuntu):
# sudo apt-get install libimage-exiftool-perl ffmpeg

# Set required environment variable
export CL_SERVER_DIR=~/.data/cl_server_data
```

### Installation

```bash
# Clone and navigate to the store service
cd services/store

# Install dependencies (uv will create .venv automatically)
uv sync

# Run database migrations
uv run alembic upgrade head
```

### Starting the Server

```bash
# Development mode (with auto-reload)
uv run store --reload

# Production mode
uv run store --port 8001

# Custom configuration
uv run store --host 0.0.0.0 --port 8080 --no-auth
```

The service will:
1. Run database migrations (unless --no-migrate is specified)
2. Start the FastAPI server
3. Be accessible at `http://localhost:8001`

### Available Commands

```bash
uv run store --help             # Show all options
uv run pytest                   # Run tests
uv run alembic upgrade head     # Run migrations
uv run alembic revision --autogenerate -m "description"  # Create migration
```

## Environment Variables

### Required

| Variable | Description | Default |
|----------|-------------|---------|
| `CL_SERVER_DIR` | Path to persistent data directory (database, media, logs) | **Required** |

### Optional Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | SQLite database location | `$CL_SERVER_DIR/media_store.db` |
| `MEDIA_STORAGE_DIR` | Directory for storing media files | `$CL_SERVER_DIR/media` |
| `PUBLIC_KEY_PATH` | ECDSA public key for verifying tokens | `$CL_SERVER_DIR/public_key.pem` |
| `AUTH_DISABLED` | Disable authentication (demo mode) | `false` |
| `READ_AUTH_ENABLED` | Require authentication for read APIs | `false` |

**Note:** The public key (`public_key.pem`) should be obtained from the authentication service for JWT token verification.

## Features

### Media Management
- **Media Management**: Upload, update, and delete media files (images, videos)
- **Collections**: Organize media into hierarchical collections
- **Metadata Extraction**: Automatic extraction of file metadata (dimensions, duration, MIME type, etc.) using ExifTool and ffprobe
- **Versioning**: Track changes to entities with SQLAlchemy-Continuum
- **Duplicate Detection**: Perceptual hash-based duplicate detection (SHA-512 for images/videos, MD5 for other files)
- **Pagination**: Efficient pagination for large media libraries
- **Search**: Query and filter media entities

### Job Management
- **Job Creation**: Create compute jobs with file uploads and external file references
- **Job Tracking**: Monitor job status and progress in real-time
- **Job Cleanup**: Manage storage by removing old jobs automatically
- **Priority-based Processing**: Support for job priority levels (0-10)
- **File Management**: Organize input/output files separately per job

### Security & Flexibility
- **Flexible Authentication**: Optional JWT-based authentication with three modes:
  - No authentication (demo mode)
  - Write-only authentication (read operations public, write operations require token)
  - Full authentication (all operations require token)
- **Granular Permissions**: Support for multiple permission types:
  - `media_store_read` - Read media entities
  - `media_store_write` - Write/modify media entities
  - `ai_inference_support` - Create/manage compute jobs
  - `admin` - Administrative operations

## API Endpoints

All endpoints return JSON responses. The service runs on port 8001.

### Public Endpoints (No Authentication Required by Default)

#### 1. Health Check
```
GET /
```

**Response:**
```json
{
  "status": "healthy",
  "service": "CoLAN Store Server",
  "version": "v1"
}
```

**Example:**
```bash
curl http://localhost:8001/
```

---

#### 2. Get Entities (List/Search)
```
GET /entities?page=1&page_size=20
```

**Query Parameters:**
- `page` (optional, default: 1) - Page number (1-indexed)
- `page_size` (optional, default: 20, max: 100) - Items per page
- `version` (optional) - Specific version number to retrieve
- `search_query` (optional) - Search query string

**Response (200):**
```json
{
  "items": [
    {
      "id": 1,
      "is_collection": false,
      "label": "Vacation Photo",
      "description": "Beach sunset",
      "parent_id": null,
      "added_date": 1704067200000,
      "updated_date": 1704067200000,
      "is_deleted": false,
      "create_date": 1704067200000,
      "added_by": "admin",
      "updated_by": "admin",
      "file_size": 2048576,
      "height": 1920,
      "width": 1080,
      "duration": null,
      "mime_type": "image/jpeg",
      "type": "image",
      "extension": "jpg",
      "md5": "5d41402abc4b2a76b9719d911017c592",
      "file_path": "/media/2024/01/vacation.jpg"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_items": 1,
    "total_pages": 1,
    "has_next": false,
    "has_prev": false
  }
}
```

**Status Codes:**
- `200 OK` - Entities retrieved successfully
- `401 Unauthorized` - Missing or invalid token (if READ_AUTH_ENABLED=true)

**Examples:**

When `READ_AUTH_ENABLED=false` (default - no authentication required):
```bash
# Public access - no token needed
curl "http://localhost:8001/entities?page=1&page_size=20"
```

When `READ_AUTH_ENABLED=true` (authentication required):
```bash
# Requires valid JWT token
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8001/entities?page=1&page_size=20"
```

---

#### 3. Get Entity by ID
```
GET /entities/{entity_id}
```

**Query Parameters:**
- `version` (optional) - Specific version number to retrieve
- `content` (optional) - Content query parameter

**Response (200):**
```json
{
  "id": 1,
  "is_collection": false,
  "label": "Vacation Photo",
  "description": "Beach sunset",
  "parent_id": null,
  "added_date": 1704067200000,
  "updated_date": 1704067200000,
  "is_deleted": false,
  "create_date": 1704067200000,
  "added_by": "admin",
  "updated_by": "admin",
  "file_size": 2048576,
  "height": 1920,
  "width": 1080,
  "mime_type": "image/jpeg",
  "type": "image",
  "extension": "jpg",
  "md5": "5d41402abc4b2a76b9719d911017c592",
  "file_path": "/media/2024/01/vacation.jpg"
}
```

**Status Codes:**
- `200 OK` - Entity found
- `401 Unauthorized` - Missing or invalid token (if READ_AUTH_ENABLED=true)
- `404 Not Found` - Entity does not exist

**Examples:**

When `READ_AUTH_ENABLED=false` (default - no authentication required):
```bash
# Public access - no token needed
curl http://localhost:8001/entities/1
```

When `READ_AUTH_ENABLED=true` (authentication required):
```bash
# Requires valid JWT token
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/entities/1
```

---

#### 4. Get Entity Versions
```
GET /entities/{entity_id}/versions
```

Returns version history for a specific entity.

**Response (200):**
```json
[
  {
    "version": 1,
    "transaction_id": 1,
    "end_transaction_id": null,
    "operation_type": 0,
    "label": "Vacation Photo",
    "description": "Beach sunset"
  }
]
```

**Status Codes:**
- `200 OK` - Versions retrieved
- `401 Unauthorized` - Missing or invalid token (if READ_AUTH_ENABLED=true)
- `404 Not Found` - Entity does not exist

**Examples:**

When `READ_AUTH_ENABLED=false` (default - no authentication required):
```bash
# Public access - no token needed
curl http://localhost:8001/entities/1/versions
```

When `READ_AUTH_ENABLED=true` (authentication required):
```bash
# Requires valid JWT token
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/entities/1/versions
```

---

### Protected Endpoints (Require Valid JWT Token)

Include the token in the `Authorization` header:
```
Authorization: Bearer <token>
```

**Note:** These endpoints require authentication when `AUTH_DISABLED=false` (default).

#### 5. Create Entity
```
POST /entities
```

**Request Body (multipart/form-data):**
```
is_collection: boolean (required)
label: string (optional)
description: string (optional)
parent_id: integer (optional)
image: file (optional) - Media file to upload
```

**Response (201):**
```json
{
  "id": 2,
  "is_collection": false,
  "label": "New Photo",
  "description": "Description",
  "parent_id": null,
  "added_date": 1704067200000,
  "updated_date": 1704067200000,
  "is_deleted": false,
  "create_date": 1704067200000,
  "added_by": "admin",
  "file_size": 1024000,
  "height": 1080,
  "width": 1920,
  "mime_type": "image/jpeg",
  "type": "image",
  "extension": "jpg",
  "md5": "098f6bcd4621d373cade4e832627b4f6",
  "file_path": "/media/2024/01/new_photo.jpg"
}
```

**Status Codes:**
- `201 Created` - Entity created successfully
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - User lacks write permission
- `422 Unprocessable Entity` - Invalid request format

**Example:**
```bash
curl -X POST http://localhost:8001/entities \
  -H "Authorization: Bearer $TOKEN" \
  -F "is_collection=false" \
  -F "label=New Photo" \
  -F "description=My new photo" \
  -F "image=@/path/to/photo.jpg"
```

---

#### 6. Update Entity (PUT)
```
PUT /entities/{entity_id}
```

**Request Body (multipart/form-data):**
```
is_collection: boolean (required)
label: string (required)
description: string (optional)
parent_id: integer (optional)
image: file (optional) - New media file
```

**Response (200):**
```json
{
  "id": 2,
  "is_collection": false,
  "label": "Updated Photo",
  "description": "Updated description",
  "parent_id": null,
  "updated_date": 1704070800000,
  "updated_by": "admin"
}
```

**Status Codes:**
- `200 OK` - Entity updated successfully
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - User lacks write permission
- `404 Not Found` - Entity does not exist

**Example:**
```bash
curl -X PUT http://localhost:8001/entities/2 \
  -H "Authorization: Bearer $TOKEN" \
  -F "is_collection=false" \
  -F "label=Updated Photo" \
  -F "description=Updated description"
```

---

#### 7. Patch Entity (PATCH)
```
PATCH /entities/{entity_id}
```

**Request Body (JSON):**
```json
{
  "label": "Patched Label",
  "description": "Patched description",
  "parent_id": 1,
  "is_deleted": false
}
```

All fields are optional. Only provided fields will be updated.

**Response (200):**
```json
{
  "id": 2,
  "label": "Patched Label",
  "description": "Patched description",
  "parent_id": 1,
  "is_deleted": false,
  "updated_date": 1704074400000
}
```

**Status Codes:**
- `200 OK` - Entity patched successfully
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - User lacks write permission
- `404 Not Found` - Entity does not exist

**Example:**
```bash
curl -X PATCH http://localhost:8001/entities/2 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"label": "Patched Label"}'
```

---

#### 8. Delete Entity
```
DELETE /entities/{entity_id}
```

**Response (204):**
No content returned on success

**Status Codes:**
- `204 No Content` - Entity deleted successfully
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - User lacks write permission
- `404 Not Found` - Entity does not exist

**Example:**
```bash
curl -X DELETE http://localhost:8001/entities/2 \
  -H "Authorization: Bearer $TOKEN"
```

---

#### 9. Delete Collection
```
DELETE /entities/collection
```

Deletes all entities in the collection.

**Response (204):**
No content returned on success

**Status Codes:**
- `204 No Content` - Collection deleted successfully
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - User lacks write permission

**Example:**
```bash
curl -X DELETE http://localhost:8001/entities/collection \
  -H "Authorization: Bearer $TOKEN"
```

---

## Job Management Endpoints

These endpoints manage compute jobs for task processing. All job endpoints require authentication with `ai_inference_support` permission.

### Protected Endpoints (Require JWT Token with ai_inference_support Permission)

Include the token in the `Authorization` header:
```
Authorization: Bearer <token>
```

#### Job: Create Job
```
POST /compute/jobs/{task_type}
```

**Request Body (multipart/form-data):**
```
upload_files: file[] (optional) - Files to upload
external_files: JSON string (optional) - Array of external file references
  Example: [{"path": "/path/to/file", "metadata": {"name": "file.txt"}}]
priority: integer (optional, default: 5, range: 0-10) - Job priority level
```

**Response (201):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "task_type": "image_resize",
  "status": "pending",
  "progress": 0,
  "input_files": [
    {
      "filename": "photo.jpg",
      "path": "jobs/550e8400-e29b-41d4-a716-446655440000/input/photo.jpg",
      "size": 2048576,
      "hash": "abc123def456"
    }
  ],
  "output_files": [],
  "task_output": null,
  "created_at": 1704067200000
}
```

**Status Codes:**
- `201 Created` - Job created successfully
- `400 Bad Request` - Missing required files or invalid request
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - User lacks ai_inference_support permission

**Example:**
```bash
curl -X POST http://localhost:8001/compute/jobs/image_resize \
  -H "Authorization: Bearer $TOKEN" \
  -F "upload_files=@photo.jpg" \
  -F "priority=5"
```

---

#### Job: Get Job Status
```
GET /compute/jobs/{job_id}
```

**Response (200):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "task_type": "image_resize",
  "status": "completed",
  "progress": 100,
  "input_files": [...],
  "output_files": [...],
  "task_output": {"width": 800, "height": 600},
  "created_at": 1704067200000,
  "started_at": 1704067210000,
  "completed_at": 1704067250000,
  "error_message": null
}
```

**Status Codes:**
- `200 OK` - Job found
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - User lacks ai_inference_support permission
- `404 Not Found` - Job does not exist

**Example:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/compute/jobs/550e8400-e29b-41d4-a716-446655440000
```

---

#### Job: Delete Job
```
DELETE /compute/jobs/{job_id}
```

Deletes the job and all associated files.

**Response (204):**
No content returned on success

**Status Codes:**
- `204 No Content` - Job deleted successfully
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - User lacks ai_inference_support permission
- `404 Not Found` - Job does not exist

**Example:**
```bash
curl -X DELETE http://localhost:8001/compute/jobs/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $TOKEN"
```

---

### Admin Job Endpoints (Require JWT Token with admin Permission)

#### Admin: Get Storage Size
```
GET /admin/compute/jobs/storage/size
```

Returns total storage usage for all jobs.

**Response (200):**
```json
{
  "total_size": 1073741824,
  "job_count": 42
}
```

**Status Codes:**
- `200 OK` - Storage info retrieved
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - User lacks admin permission

**Example:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/admin/compute/jobs/storage/size
```

---

#### Admin: Cleanup Old Jobs
```
DELETE /admin/compute/jobs/cleanup
```

Deletes jobs older than specified number of days.

**Query Parameters:**
- `days` (optional, default: 7, minimum: 1) - Delete jobs older than N days

**Response (200):**
```json
{
  "deleted_count": 12,
  "freed_space": 536870912
}
```

**Status Codes:**
- `200 OK` - Cleanup completed
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - User lacks admin permission

**Example:**
```bash
curl -X DELETE "http://localhost:8001/admin/compute/jobs/cleanup?days=30" \
  -H "Authorization: Bearer $TOKEN"
```

---

#### Job: Get Worker Capabilities
```
GET /compute/capabilities
```

Returns available worker capabilities and their counts. This endpoint does not require authentication.

**Response (200):**
```json
{
  "num_workers": 6,
  "capabilities": {
    "image_resize": 2,
    "image_conversion": 1,
    "video_processing": 3
  }
}
```

- `num_workers`: Number of unique connected workers (0 if none available)
- `capabilities`: Dictionary mapping capability names to available idle worker counts

**Status Codes:**
- `200 OK` - Capabilities retrieved successfully

**Example:**
```bash
curl http://localhost:8001/compute/capabilities
```

---

### Admin Endpoints (Require Valid Token + Write Permission)

#### 10. Get Configuration
```
GET /admin/config
```

Returns current service configuration.

**Response (200):**
```json
{
  "read_auth_enabled": false,
  "updated_at": 1704067200000,
  "updated_by": "admin"
}
```

**Status Codes:**
- `200 OK` - Configuration retrieved
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - User lacks write permission

**Example:**
```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8001/admin/config
```

---

#### 11. Update Read Authentication Config
```
PUT /admin/config/read-auth
```

**Request Body (JSON):**
```json
{
  "enabled": true
}
```

**Response (200):**
```json
{
  "read_auth_enabled": true,
  "updated_at": 1704070800000,
  "updated_by": "admin"
}
```

**Status Codes:**
- `200 OK` - Configuration updated
- `401 Unauthorized` - Missing or invalid token
- `403 Forbidden` - User lacks write permission

**Example:**
```bash
curl -X PUT http://localhost:8001/admin/config/read-auth \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

---

## Authentication Flow

### Step 1: Obtain a Token from Auth Service

First, get a token from the authentication service (port 8000):

```bash
TOKEN=$(curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin" \
  | jq -r '.access_token')

echo $TOKEN
```

### Step 2: Use Token for Authenticated Requests

Include the token in the `Authorization` header:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/entities
```

### Authentication Modes

The store service supports three flexible authentication modes:

#### 1. No Authentication (`AUTH_DISABLED=true`)
- **All endpoints** are publicly accessible without tokens
- Useful for development and testing
- Start with: `./start.sh --no-auth`

#### 2. Write-Only Authentication (default: `AUTH_DISABLED=false`, `READ_AUTH_ENABLED=false`)
- **Read endpoints** (GET) are publicly accessible without tokens
  - `GET /entities` - List entities
  - `GET /entities/{id}` - Get entity by ID
  - `GET /entities/{id}/versions` - Get entity versions
- **Write endpoints** (POST, PUT, PATCH, DELETE) require valid JWT tokens
- This is the **default mode** when you run `./start.sh`

#### 3. Full Authentication (`READ_AUTH_ENABLED=true`)
- **All endpoints** require valid JWT tokens (both read and write)
- Enable by setting environment variable: `READ_AUTH_ENABLED=true`
- Or configure at runtime via: `PUT /config/read-auth`
- Most secure mode for production deployments

### Token Details

- **Format:** JWT (JSON Web Token)
- **Algorithm:** ES256 (ECDSA with SHA-256)
- **Verification:** Uses public key from authentication service
- **Permissions:** Requires appropriate read/write permissions based on endpoint

## Error Handling

All error responses include a JSON body with error details.

### HTTP Status Codes

| Status | Meaning | When It Occurs |
|--------|---------|----------------|
| `400 Bad Request` | Invalid request format | Malformed JSON or missing required fields |
| `401 Unauthorized` | Missing or invalid authentication | No token provided, expired token, invalid token |
| `403 Forbidden` | Valid token but insufficient permissions | User lacks required permissions |
| `404 Not Found` | Resource does not exist | Entity ID doesn't exist, invalid endpoint |
| `422 Unprocessable Entity` | Invalid request data | Invalid field values, constraint violations |
| `500 Internal Server Error` | Server-side error | Unexpected server error |

### Example Error Responses

**Missing Authentication (401):**
```json
{
  "detail": "Not authenticated"
}
```

**Insufficient Permissions (403):**
```json
{
  "detail": "Not enough permissions"
}
```

**Entity Not Found (404):**
```json
{
  "detail": "Entity not found"
}
```

**Invalid Request (422):**
```json
{
  "detail": [
    {
      "loc": ["body", "is_collection"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### Client Error Handling

Implement these checks in your client:

1. **Check for 401 errors** - Token may have expired. Re-authenticate and obtain a new token.
2. **Check for 403 errors** - User doesn't have required permissions. Verify user has write permissions.
3. **Check for 404 errors** - Resource doesn't exist. Verify entity ID exists before operating on it.
4. **Handle 422 errors** - Validate request format and required fields match the documentation.
5. **Retry on 500 errors** - Implement exponential backoff for temporary server errors.

## Troubleshooting

### Port 8001 Already in Use

If you see an error like "Address already in use":

```bash
# Find process using port 8001
lsof -i :8001

# Kill the process (if safe to do so)
kill -9 <PID>
```

### Missing Environment Variables

If the service fails to start with an error about missing variables:

```bash
# Check required variables are set
echo $CL_VENV_DIR
echo $CL_SERVER_DIR

# Set them if missing
export CL_VENV_DIR=/path/to/venv/dir
export CL_SERVER_DIR=/path/to/data/dir

# Then run start.sh again
./start.sh
```

### Authentication Failures (401/403)

**Issue:** Getting "Not authenticated" errors

**Solutions:**
- Verify token is included in `Authorization: Bearer <token>` header
- Check that token hasn't expired (default 30 min lifetime)
- Get a new token from the auth service
- Verify the public key is correctly configured

**Issue:** Getting "Not enough permissions" (403)

**Solutions:**
- Verify user has write permission for write endpoints
- Check user permissions using auth service `GET /users/me`
- Ask an admin to update user permissions

### Database Errors on Startup

If you see SQLite errors on startup:

```bash
# The database is usually locked - check if another instance is running
ps aux | grep python

# Or delete the database to recreate it (loses all data)
rm $CL_SERVER_DIR/media_store.db
./start.sh
```

### Media Storage Issues

If you see errors about media storage:

1. Verify `CL_SERVER_DIR` is set and directory exists
2. Ensure directory has write permissions
3. Check available disk space
4. Verify `MEDIA_STORAGE_DIR` path is accessible

### Public Key Not Found

If you see errors about missing `public_key.pem`:

1. Ensure the authentication service has generated the key pair
2. Copy `public_key.pem` from auth service to `$CL_SERVER_DIR`
3. Verify `PUBLIC_KEY_PATH` environment variable points to the correct location
4. Or run with `--no-auth` for testing without authentication

## Integration Example

Here's a complete example of a Python client integrating with this service:

```python
import requests
import json

# Configuration
AUTH_SERVER = "http://localhost:8000"
STORE_SERVER = "http://localhost:8001"
USERNAME = "admin"
PASSWORD = "admin"

# Step 1: Get token from auth service
response = requests.post(
    f"{AUTH_SERVER}/auth/token",
    data={"username": USERNAME, "password": PASSWORD}
)
response.raise_for_status()
token = response.json()["access_token"]

# Step 2: Use token for authenticated requests
headers = {"Authorization": f"Bearer {token}"}

# List entities
entities_response = requests.get(
    f"{STORE_SERVER}/entities?page=1&page_size=20",
    headers=headers
)
print("Entities:", entities_response.json())

# Upload a new media file
with open("photo.jpg", "rb") as f:
    files = {"image": f}
    data = {
        "is_collection": False,
        "label": "My Photo",
        "description": "A beautiful photo"
    }
    create_response = requests.post(
        f"{STORE_SERVER}/entities",
        files=files,
        data=data,
        headers=headers
    )
print("Created entity:", create_response.json())

# Get entity by ID
entity_id = create_response.json()["id"]
entity_response = requests.get(
    f"{STORE_SERVER}/entities/{entity_id}",
    headers=headers
)
print("Entity details:", entity_response.json())

# Update entity metadata
patch_data = {
    "label": "Updated Photo Label",
    "description": "Updated description"
}
update_response = requests.patch(
    f"{STORE_SERVER}/entities/{entity_id}",
    json=patch_data,
    headers=headers
)
print("Updated entity:", update_response.json())

# Handle token expiration
try:
    response = requests.get(f"{STORE_SERVER}/entities", headers=headers)
    response.raise_for_status()
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 401:
        # Token expired, get new one
        print("Token expired, re-authenticating...")
        response = requests.post(
            f"{AUTH_SERVER}/auth/token",
            data={"username": USERNAME, "password": PASSWORD}
        )
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
```

## Architecture

### Technology Stack

- **Framework:** FastAPI
- **Database:** SQLite with SQLAlchemy ORM
- **Versioning:** SQLAlchemy-Continuum
- **Media Processing:** cl_ml_tools.algorithms (perceptual hashing, EXIF extraction)
- **Metadata Tools:** ExifTool (EXIF data), ffprobe (video duration)
- **Authentication:** JWT with ES256 (ECDSA) signature verification

### Directory Structure

```
cl_server_store_service/
├── src/
│   ├── __init__.py          # FastAPI app initialization
│   ├── routes.py            # API endpoint definitions
│   ├── service.py           # Business logic layer
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py           # Pydantic schemas
│   ├── database.py          # Database configuration
│   ├── auth.py              # Authentication logic
│   ├── config.py            # Configuration management
│   ├── config_service.py    # Configuration service
│   ├── file_storage.py      # File storage management
│   └── versioning.py        # Versioning setup
├── alembic/                 # Database migrations
├── tests/                   # Test suite
├── start.sh                 # Service startup script
├── common.sh                # Common utilities
└── README.md                # This file
```

### Data Model

The service manages two main entity types:

1. **Collections**: Containers for organizing media (folders)
2. **Media Items**: Individual media files (images, videos)

Each entity includes:
- Metadata (label, description, timestamps)
- File information (size, dimensions, MIME type, MD5 hash)
- Versioning information (tracked automatically)
- User tracking (added_by, updated_by)
- Hierarchical relationships (parent_id)
