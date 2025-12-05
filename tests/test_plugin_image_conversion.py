"""
Tests for image_conversion plugin route.

This test file covers:
- Job creation (valid data, validation errors)
- Job retrieval (GET)
- Job deletion (DELETE)
- Authentication (401 without token)
- Authorization (403 with wrong permission)
- Job lifecycle
- Format-specific tests (PNG, JPEG, WebP, etc.)
"""

import io
import pytest
from PIL import Image


class TestImageConversionJobCreation:
    """Test image_conversion job creation functionality."""

    @pytest.fixture
    def sample_image_file(self):
        """Create a simple test image in memory."""
        img = Image.new('RGB', (100, 100), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes

    @pytest.fixture
    def sample_rgba_image_file(self):
        """Create a test image with alpha channel."""
        img = Image.new('RGBA', (100, 100), color=(255, 0, 0, 128))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes

    def test_create_job_convert_to_webp(self, client, sample_image_file):
        """Test creating a conversion job to WebP format."""
        response = client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "webp",
                "quality": 85,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 200
        data = response.json()

        assert "job_id" in data
        assert data["status"] == "queued"
        assert data["job_id"] is not None

    def test_create_job_convert_to_jpeg(self, client, sample_image_file):
        """Test creating a conversion job to JPEG format."""
        response = client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "jpg",
                "quality": 90,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"

    def test_create_job_convert_to_png(self, client, sample_image_file):
        """Test creating a conversion job to PNG format."""
        response = client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "png",
                "quality": 85,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 200

    def test_create_job_convert_to_gif(self, client, sample_image_file):
        """Test creating a conversion job to GIF format."""
        response = client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "gif",
                "quality": 85,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 200

    def test_create_job_convert_to_bmp(self, client, sample_image_file):
        """Test creating a conversion job to BMP format."""
        response = client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "bmp",
                "quality": 85,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 200

    def test_create_job_convert_to_tiff(self, client, sample_image_file):
        """Test creating a conversion job to TIFF format."""
        response = client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "tiff",
                "quality": 85,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 200

    def test_create_job_with_high_quality(self, client, sample_image_file):
        """Test creating a conversion job with high quality."""
        response = client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "webp",
                "quality": 100,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 200

    def test_create_job_with_low_quality(self, client, sample_image_file):
        """Test creating a conversion job with low quality."""
        response = client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "webp",
                "quality": 1,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 200

    def test_create_job_with_high_priority(self, client, sample_image_file):
        """Test creating a conversion job with high priority."""
        response = client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "webp",
                "quality": 85,
                "priority": 10,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 200

    def test_create_job_invalid_format(self, client, sample_image_file):
        """Test that creating a job with invalid format fails."""
        response = client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "invalid_format",
                "quality": 85,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 422

    def test_create_job_invalid_quality_zero(self, client, sample_image_file):
        """Test that creating a job with quality=0 fails."""
        response = client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "webp",
                "quality": 0,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 422

    def test_create_job_invalid_quality_over_100(self, client, sample_image_file):
        """Test that creating a job with quality>100 fails."""
        response = client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "webp",
                "quality": 101,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 422

    def test_create_job_invalid_priority(self, client, sample_image_file):
        """Test that creating a job with invalid priority fails."""
        response = client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "webp",
                "quality": 85,
                "priority": 15,  # Invalid: max is 10
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 422

    def test_create_job_missing_file(self, client):
        """Test that creating a job without file fails."""
        response = client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "webp",
                "quality": 85,
                "priority": 5,
            },
        )

        assert response.status_code == 422

    def test_create_job_missing_format(self, client, sample_image_file):
        """Test that creating a job without format fails."""
        response = client.post(
            "/compute/jobs/image_conversion",
            data={
                "quality": 85,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 422


class TestImageConversionJobRetrieval:
    """Test image_conversion job retrieval functionality."""

    @pytest.fixture
    def sample_image_file(self):
        """Create a simple test image in memory."""
        img = Image.new('RGB', (100, 100), color='blue')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes

    def test_get_job_by_id(self, client, sample_image_file):
        """Test retrieving a job by ID."""
        # Create job
        create_response = client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "webp",
                "quality": 85,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert create_response.status_code == 200
        job_id = create_response.json()["job_id"]

        # Retrieve job
        get_response = client.get(f"/compute/jobs/{job_id}")

        assert get_response.status_code == 200
        job = get_response.json()
        assert job["job_id"] == job_id
        assert job["task_type"] == "image_conversion"
        assert job["status"] == "queued"

    def test_get_nonexistent_job(self, client):
        """Test retrieving a nonexistent job returns 404."""
        response = client.get("/compute/jobs/nonexistent-job-id")

        assert response.status_code == 404


class TestImageConversionJobDeletion:
    """Test image_conversion job deletion functionality."""

    @pytest.fixture
    def sample_image_file(self):
        """Create a simple test image in memory."""
        img = Image.new('RGB', (100, 100), color='green')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes

    def test_delete_job_by_id(self, client, sample_image_file):
        """Test deleting a job by ID."""
        # Create job
        create_response = client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "webp",
                "quality": 85,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        job_id = create_response.json()["job_id"]

        # Delete job
        delete_response = client.delete(f"/compute/jobs/{job_id}")

        assert delete_response.status_code == 204

        # Verify job is deleted
        get_response = client.get(f"/compute/jobs/{job_id}")
        assert get_response.status_code == 404

    def test_delete_nonexistent_job(self, client):
        """Test deleting a nonexistent job returns 404."""
        response = client.delete("/compute/jobs/nonexistent-job-id")

        assert response.status_code == 404


class TestImageConversionJobLifecycle:
    """Test complete job lifecycle for image_conversion."""

    @pytest.fixture
    def sample_image_file(self):
        """Create a simple test image in memory."""
        img = Image.new('RGB', (100, 100), color='yellow')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes

    def test_create_retrieve_delete_lifecycle(self, client, sample_image_file):
        """Test creating, retrieving, and deleting a job."""
        # Create
        create_response = client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "webp",
                "quality": 85,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert create_response.status_code == 200
        job_id = create_response.json()["job_id"]

        # Retrieve
        get_response = client.get(f"/compute/jobs/{job_id}")
        assert get_response.status_code == 200
        assert get_response.json()["status"] == "queued"

        # Delete
        delete_response = client.delete(f"/compute/jobs/{job_id}")
        assert delete_response.status_code == 204

        # Verify deletion
        get_after_delete = client.get(f"/compute/jobs/{job_id}")
        assert get_after_delete.status_code == 404


class TestImageConversionAuthentication:
    """Test authentication requirements for image_conversion endpoints."""

    @pytest.fixture
    def sample_image_file(self):
        """Create a simple test image in memory."""
        img = Image.new('RGB', (100, 100), color='purple')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes

    def test_create_job_without_token_returns_401(self, auth_client, sample_image_file):
        """Test that creating a job without token returns 401."""
        response = auth_client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "webp",
                "quality": 85,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 401

    def test_get_job_without_token_returns_401(self, auth_client):
        """Test that getting a job without token returns 401."""
        response = auth_client.get("/compute/jobs/test-job-id")

        assert response.status_code == 401

    def test_delete_job_without_token_returns_401(self, auth_client):
        """Test that deleting a job without token returns 401."""
        response = auth_client.delete("/compute/jobs/test-job-id")

        assert response.status_code == 401

    def test_invalid_token_returns_401(self, auth_client, sample_image_file):
        """Test that invalid token returns 401."""
        response = auth_client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "webp",
                "quality": 85,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
            headers={"Authorization": "Bearer invalid.token.here"},
        )

        assert response.status_code == 401


class TestImageConversionAuthorization:
    """Test authorization requirements for image_conversion endpoints."""

    @pytest.fixture
    def sample_image_file(self):
        """Create a simple test image in memory."""
        img = Image.new('RGB', (100, 100), color='orange')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes

    def test_create_job_with_write_permission_fails(
        self, auth_client, write_token, sample_image_file
    ):
        """Test that write permission is insufficient for job creation."""
        response = auth_client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "webp",
                "quality": 85,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
            headers={"Authorization": f"Bearer {write_token}"},
        )

        assert response.status_code == 403

    def test_create_job_with_read_permission_fails(
        self, auth_client, read_token, sample_image_file
    ):
        """Test that read permission is insufficient for job creation."""
        response = auth_client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "webp",
                "quality": 85,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
            headers={"Authorization": f"Bearer {read_token}"},
        )

        assert response.status_code == 403

    def test_get_job_with_wrong_permission_fails(self, auth_client, write_token):
        """Test that wrong permission fails for job retrieval."""
        response = auth_client.get(
            "/compute/jobs/some-job-id",
            headers={"Authorization": f"Bearer {write_token}"},
        )

        assert response.status_code == 403

    def test_delete_job_with_wrong_permission_fails(self, auth_client, write_token):
        """Test that wrong permission fails for job deletion."""
        response = auth_client.delete(
            "/compute/jobs/some-job-id",
            headers={"Authorization": f"Bearer {write_token}"},
        )

        assert response.status_code == 403

    def test_create_job_with_inference_permission_succeeds(
        self, auth_client, inference_token, sample_image_file
    ):
        """Test that ai_inference_support permission allows job creation."""
        response = auth_client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "webp",
                "quality": 85,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert response.status_code == 200


class TestImageConversionTokenValidation:
    """Test JWT token validation for image_conversion endpoints."""

    @pytest.fixture
    def sample_image_file(self):
        """Create a simple test image in memory."""
        img = Image.new('RGB', (100, 100), color='cyan')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes

    def test_expired_token_returns_401(
        self, auth_client, jwt_token_generator, sample_image_file
    ):
        """Test that expired token returns 401."""
        expired_token = jwt_token_generator.generate_token(
            sub="testuser", permissions=["ai_inference_support"], expired=True
        )

        response = auth_client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "webp",
                "quality": 85,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
            headers={"Authorization": f"Bearer {expired_token}"},
        )

        assert response.status_code == 401

    def test_token_with_wrong_signature_returns_401(
        self, auth_client, jwt_token_generator, sample_image_file
    ):
        """Test that token with wrong signature returns 401."""
        wrong_token = jwt_token_generator.generate_invalid_token_wrong_key()

        response = auth_client.post(
            "/compute/jobs/image_conversion",
            data={
                "format": "webp",
                "quality": 85,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
            headers={"Authorization": f"Bearer {wrong_token}"},
        )

        assert response.status_code == 401
