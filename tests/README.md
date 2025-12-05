# Test Suite Documentation

This directory contains tests for the cl_server_store_service.

## Test Structure

```
tests/
├── conftest.py                      # Shared fixtures
├── test_config.py                   # Test configuration
├── test_plugin_template.py.template # Template for new plugin tests
├── test_plugin_image_resize.py      # Image resize plugin tests
├── test_plugin_image_conversion.py  # Image conversion plugin tests
├── test_plugin_routes.py            # Plugin discovery tests
├── test_job_auth.py                 # [SKIPPED] Legacy auth tests
├── test_job_crud.py                 # [SKIPPED] Legacy CRUD tests
└── README.md                        # This file
```

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific plugin tests
pytest tests/test_plugin_image_resize.py -v
pytest tests/test_plugin_image_conversion.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Run only authentication tests
pytest tests/ -v -k "Authentication"

# Run only authorization tests
pytest tests/ -v -k "Authorization"
```

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

## Fixtures

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

## Example: Complete Watermark Plugin Test

```python
"""Tests for watermark plugin route."""

import io
import pytest
from PIL import Image

PLUGIN_NAME = "watermark"
TASK_TYPE = "watermark"
ENDPOINT = "/compute/jobs/watermark"

VALID_JOB_DATA = {
    "priority": 5,
    "watermark_text": "Copyright 2024",
    "position": "bottom-right",
    "opacity": 0.5,
}


@pytest.fixture
def sample_image_file():
    img = Image.new('RGB', (100, 100), color='red')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes


class TestWatermarkJobCreation:
    def test_create_job_with_valid_data(self, client, sample_image_file):
        response = client.post(
            ENDPOINT,
            data=VALID_JOB_DATA,
            files={"file": ("test.png", sample_image_file, "image/png")},
        )
        assert response.status_code == 200

    def test_create_job_invalid_position(self, client, sample_image_file):
        response = client.post(
            ENDPOINT,
            data={**VALID_JOB_DATA, "position": "invalid"},
            files={"file": ("test.png", sample_image_file, "image/png")},
        )
        assert response.status_code == 422

    def test_create_job_invalid_opacity(self, client, sample_image_file):
        response = client.post(
            ENDPOINT,
            data={**VALID_JOB_DATA, "opacity": 1.5},
            files={"file": ("test.png", sample_image_file, "image/png")},
        )
        assert response.status_code == 422


# ... continue with other test classes from template
```

## Skipped Tests

The following test files are skipped because they test the removed generic endpoint:

- `test_job_auth.py` - Tests `/compute/jobs/{task_type}` (removed)
- `test_job_crud.py` - Tests `/compute/jobs/{task_type}` (removed)

These endpoints have been replaced by plugin-specific routes (e.g., `/compute/jobs/image_resize`).

The functionality is now covered by:
- `test_plugin_image_resize.py`
- `test_plugin_image_conversion.py`

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
