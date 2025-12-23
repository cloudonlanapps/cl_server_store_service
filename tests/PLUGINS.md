# Plugin Testing Guide

This document explains how to create and test compute plugins for the CL Server Store Service.

## Test Categories

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

## Test Class Structure

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

## Plugin Discovery Tests

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

## Available Fixtures

### `client` (conftest.py)

Test client with authentication **bypassed**. Use for functional tests.

```python
def test_something(self, client):
    response = client.post("/compute/jobs/image_resize", ...)
    assert response.status_code == 200
```

### `auth_client` (conftest.py)

Test client with authentication **enabled**. Use for auth/permission tests.

```python
def test_requires_token(self, auth_client):
    response = auth_client.post("/compute/jobs/image_resize", ...)
    assert response.status_code == 401  # No token
```

### Token Fixtures

| Fixture | Permission | Admin |
|---------|-----------|-------|
| `inference_token` | `ai_inference_support` | No |
| `inference_admin_token` | `ai_inference_support` | Yes |
| `write_token` | `media_store_write` | No |
| `read_token` | `media_store_read` | No |
| `admin_token` | `media_store_read`, `media_store_write` | Yes |

### Fixture Usage Guidelines

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

## HTTP Status Code Reference

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

## Creating Tests for a New Plugin

### Step 1: Copy the Template

```bash
cp tests/test_plugin_template.py.template tests/test_plugin_<plugin_name>.py
```

### Step 2: Replace Placeholders

Edit the new file and replace:

| Placeholder | Replace With | Example |
|-------------|-------------|---------|
| `{{PLUGIN_NAME}}` | Plugin name | `watermark` |
| `{{TASK_TYPE}}` | Task type string | `watermark` |
| `{{ENDPOINT}}` | API endpoint | `/compute/jobs/watermark` |

### Step 3: Update Configuration

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

### Step 4: Add Plugin-Specific Tests

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

### Step 5: Modify Fixtures If Needed

If your plugin doesn't use images, update `sample_image_file`:

```python
@pytest.fixture
def sample_video_file(self):
    """Create a test video file."""
    # Return video bytes...
```

## Example: Image Resize Plugin Test

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

## Test Coverage Checklist

For each plugin, ensure the following are tested:

### Creation Tests
- [ ] Valid data → 200
- [ ] All optional parameters
- [ ] Each required parameter missing → 422
- [ ] Each parameter with invalid value → 422
- [ ] Missing file → 422
- [ ] Invalid priority → 422

### Retrieval Tests
- [ ] Get by ID → 200
- [ ] Nonexistent ID → 404

### Deletion Tests
- [ ] Delete by ID → 204
- [ ] Verify deletion → 404
- [ ] Nonexistent ID → 404

### Lifecycle Tests
- [ ] Create → Get → Delete → Verify

### Authentication Tests
- [ ] No token → 401
- [ ] Invalid token → 401
- [ ] Expired token → 401
- [ ] Wrong signature → 401

### Authorization Tests
- [ ] Wrong permission → 403
- [ ] Correct permission → 200

## Plugin Test Template

A test template is available at:
- `tests/test_plugin_template.py.template` - Template for new plugin tests

## Skipped Legacy Tests

The following test files are skipped because they test the removed generic endpoint:

- `test_job_auth.py` - Tests `/compute/jobs/{task_type}` (removed)
- `test_job_crud.py` - Tests `/compute/jobs/{task_type}` (removed)

These endpoints have been replaced by plugin-specific routes (e.g., `/compute/jobs/image_resize`).

The functionality is now covered by the plugin-specific tests listed above.
