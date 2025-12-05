"""
Tests for image_resize plugin route.

This test file covers:
- Job creation (valid data, validation errors)
- Job retrieval (GET)
- Job deletion (DELETE)
- Authentication (401 without token)
- Authorization (403 with wrong permission)
- Job lifecycle
"""

import io
import pytest
from PIL import Image


class TestImageResizeJobCreation:
    """Test image_resize job creation functionality."""

    @pytest.fixture
    def sample_image_file(self):
        """Create a simple test image in memory."""
        img = Image.new('RGB', (100, 100), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes

    def test_create_job_with_valid_data(self, client, sample_image_file):
        """Test creating a resize job with valid data."""
        response = client.post(
            "/compute/jobs/image_resize",
            data={
                "width": 50,
                "height": 50,
                "maintain_aspect_ratio": False,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 200
        data = response.json()

        assert "job_id" in data
        assert data["status"] == "queued"
        assert data["job_id"] is not None

    def test_create_job_with_aspect_ratio(self, client, sample_image_file):
        """Test creating a resize job with aspect ratio maintained."""
        response = client.post(
            "/compute/jobs/image_resize",
            data={
                "width": 50,
                "height": 50,
                "maintain_aspect_ratio": True,
                "priority": 7,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"

    def test_create_job_with_high_priority(self, client, sample_image_file):
        """Test creating a resize job with high priority."""
        response = client.post(
            "/compute/jobs/image_resize",
            data={
                "width": 50,
                "height": 50,
                "maintain_aspect_ratio": False,
                "priority": 10,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 200

    def test_create_job_invalid_width_zero(self, client, sample_image_file):
        """Test that creating a job with width=0 fails."""
        response = client.post(
            "/compute/jobs/image_resize",
            data={
                "width": 0,
                "height": 50,
                "maintain_aspect_ratio": False,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 422

    def test_create_job_invalid_height_zero(self, client, sample_image_file):
        """Test that creating a job with height=0 fails."""
        response = client.post(
            "/compute/jobs/image_resize",
            data={
                "width": 50,
                "height": 0,
                "maintain_aspect_ratio": False,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 422

    def test_create_job_invalid_priority(self, client, sample_image_file):
        """Test that creating a job with invalid priority fails."""
        response = client.post(
            "/compute/jobs/image_resize",
            data={
                "width": 50,
                "height": 50,
                "maintain_aspect_ratio": False,
                "priority": 15,  # Invalid: max is 10
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 422

    def test_create_job_missing_file(self, client):
        """Test that creating a job without file fails."""
        response = client.post(
            "/compute/jobs/image_resize",
            data={
                "width": 50,
                "height": 50,
                "maintain_aspect_ratio": False,
                "priority": 5,
            },
        )

        assert response.status_code == 422

    def test_create_job_missing_width(self, client, sample_image_file):
        """Test that creating a job without width fails."""
        response = client.post(
            "/compute/jobs/image_resize",
            data={
                "height": 50,
                "maintain_aspect_ratio": False,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 422

    def test_create_job_missing_height(self, client, sample_image_file):
        """Test that creating a job without height fails."""
        response = client.post(
            "/compute/jobs/image_resize",
            data={
                "width": 50,
                "maintain_aspect_ratio": False,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
        )

        assert response.status_code == 422


class TestImageResizeJobRetrieval:
    """Test image_resize job retrieval functionality."""

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
            "/compute/jobs/image_resize",
            data={
                "width": 50,
                "height": 50,
                "maintain_aspect_ratio": False,
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
        assert job["task_type"] == "image_resize"
        assert job["status"] == "queued"

    def test_get_nonexistent_job(self, client):
        """Test retrieving a nonexistent job returns 404."""
        response = client.get("/compute/jobs/nonexistent-job-id")

        assert response.status_code == 404


class TestImageResizeJobDeletion:
    """Test image_resize job deletion functionality."""

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
            "/compute/jobs/image_resize",
            data={
                "width": 50,
                "height": 50,
                "maintain_aspect_ratio": False,
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


class TestImageResizeJobLifecycle:
    """Test complete job lifecycle for image_resize."""

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
            "/compute/jobs/image_resize",
            data={
                "width": 50,
                "height": 50,
                "maintain_aspect_ratio": False,
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


class TestImageResizeAuthentication:
    """Test authentication requirements for image_resize endpoints."""

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
            "/compute/jobs/image_resize",
            data={
                "width": 50,
                "height": 50,
                "maintain_aspect_ratio": False,
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
            "/compute/jobs/image_resize",
            data={
                "width": 50,
                "height": 50,
                "maintain_aspect_ratio": False,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
            headers={"Authorization": "Bearer invalid.token.here"},
        )

        assert response.status_code == 401


class TestImageResizeAuthorization:
    """Test authorization requirements for image_resize endpoints."""

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
            "/compute/jobs/image_resize",
            data={
                "width": 50,
                "height": 50,
                "maintain_aspect_ratio": False,
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
            "/compute/jobs/image_resize",
            data={
                "width": 50,
                "height": 50,
                "maintain_aspect_ratio": False,
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
            "/compute/jobs/image_resize",
            data={
                "width": 50,
                "height": 50,
                "maintain_aspect_ratio": False,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert response.status_code == 200


class TestImageResizeTokenValidation:
    """Test JWT token validation for image_resize endpoints."""

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
            "/compute/jobs/image_resize",
            data={
                "width": 50,
                "height": 50,
                "maintain_aspect_ratio": False,
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
            "/compute/jobs/image_resize",
            data={
                "width": 50,
                "height": 50,
                "maintain_aspect_ratio": False,
                "priority": 5,
            },
            files={"file": ("test.png", sample_image_file, "image/png")},
            headers={"Authorization": f"Bearer {wrong_token}"},
        )

        assert response.status_code == 401
