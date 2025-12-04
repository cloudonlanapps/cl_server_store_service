"""
Tests for job endpoint authentication and authorization.
Tests permission enforcement for ai_inference_support permission.
"""

import pytest


class TestJobAuthenticationRequired:
    """Test that job endpoints require authentication."""

    def test_create_job_without_token_returns_401(self, auth_client, sample_job_data):
        """Test that creating a job without token returns 401."""
        response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
        )

        assert response.status_code == 401

    def test_get_job_without_token_returns_401(self, auth_client):
        """Test that getting a job without token returns 401."""
        response = auth_client.get("/jobs/test-job-id")

        assert response.status_code == 401

    def test_delete_job_without_token_returns_401(self, auth_client):
        """Test that deleting a job without token returns 401."""
        response = auth_client.delete("/jobs/test-job-id")

        assert response.status_code == 401

    def test_invalid_token_returns_401(self, auth_client, sample_job_data):
        """Test that invalid token returns 401."""
        response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": "Bearer invalid.token.here"},
        )

        assert response.status_code == 401


class TestJobPermissionRequired:
    """Test that job endpoints require ai_inference_support permission."""

    def test_create_job_with_write_permission_fails(
        self, auth_client, write_token, sample_job_data
    ):
        """Test that write permission is insufficient for job creation."""
        response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {write_token}"},
        )

        assert response.status_code == 403

    def test_create_job_with_read_permission_fails(
        self, auth_client, read_token, sample_job_data
    ):
        """Test that read permission is insufficient for job creation."""
        response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {read_token}"},
        )

        assert response.status_code == 403

    def test_get_job_with_write_permission_fails(self, auth_client, write_token):
        """Test that write permission is insufficient for job retrieval."""
        response = auth_client.get(
            "/jobs/test-job-id",
            headers={"Authorization": f"Bearer {write_token}"},
        )

        assert response.status_code == 403

    def test_get_job_with_read_permission_fails(self, auth_client, read_token):
        """Test that read permission is insufficient for job retrieval."""
        response = auth_client.get(
            "/jobs/test-job-id",
            headers={"Authorization": f"Bearer {read_token}"},
        )

        assert response.status_code == 403

    def test_delete_job_with_write_permission_fails(self, auth_client, write_token):
        """Test that write permission is insufficient for job deletion."""
        response = auth_client.delete(
            "/jobs/test-job-id",
            headers={"Authorization": f"Bearer {write_token}"},
        )

        assert response.status_code == 403

    def test_delete_job_with_read_permission_fails(self, auth_client, read_token):
        """Test that read permission is insufficient for job deletion."""
        response = auth_client.delete(
            "/jobs/test-job-id",
            headers={"Authorization": f"Bearer {read_token}"},
        )

        assert response.status_code == 403


class TestJobInferencePermission:
    """Test that ai_inference_support permission is sufficient for job endpoints."""

    def test_create_job_with_inference_permission_succeeds(
        self, auth_client, inference_token, sample_job_data
    ):
        """Test that ai_inference_support permission allows job creation."""
        response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert response.status_code == 201

    def test_get_job_with_inference_permission_succeeds(
        self, auth_client, inference_token, sample_job_data
    ):
        """Test that ai_inference_support permission allows job retrieval."""
        # Create a job first
        create_response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        job_id = create_response.json()["job_id"]

        # Retrieve the job
        get_response = auth_client.get(
            f"/jobs/{job_id}",
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert get_response.status_code == 200

    def test_delete_job_with_inference_permission_succeeds(
        self, auth_client, inference_token, sample_job_data
    ):
        """Test that ai_inference_support permission allows job deletion."""
        # Create a job first
        create_response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        job_id = create_response.json()["job_id"]

        # Delete the job
        delete_response = auth_client.delete(
            f"/jobs/{job_id}",
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert delete_response.status_code == 200


class TestAdminPermission:
    """Test that admin users have access to admin job endpoints."""

    def test_get_storage_size_without_admin_fails(self, auth_client, inference_token):
        """Test that non-admin cannot access storage size endpoint."""
        response = auth_client.get(
            "/jobs/admin/storage/size",
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert response.status_code == 403

    def test_cleanup_jobs_without_admin_fails(self, auth_client, inference_token):
        """Test that non-admin cannot access cleanup endpoint."""
        response = auth_client.delete(
            "/jobs/admin/cleanup",
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert response.status_code == 403

    def test_get_storage_size_with_admin_succeeds(
        self, auth_client, inference_admin_token
    ):
        """Test that admin can access storage size endpoint."""
        response = auth_client.get(
            "/jobs/admin/storage/size",
            headers={"Authorization": f"Bearer {inference_admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "total_size" in data
        assert "job_count" in data
        assert isinstance(data["total_size"], int)
        assert isinstance(data["job_count"], int)

    def test_cleanup_jobs_with_admin_succeeds(self, auth_client, inference_admin_token):
        """Test that admin can access cleanup endpoint."""
        response = auth_client.delete(
            "/jobs/admin/cleanup?days=1",
            headers={"Authorization": f"Bearer {inference_admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "deleted_count" in data
        assert "freed_space" in data


class TestTokenValidation:
    """Test JWT token validation for job endpoints."""

    def test_expired_token_returns_401(
        self, auth_client, jwt_token_generator, sample_job_data
    ):
        """Test that expired token returns 401."""
        expired_token = jwt_token_generator.generate_token(
            sub="testuser", permissions=["ai_inference_support"], expired=True
        )

        response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {expired_token}"},
        )

        assert response.status_code == 401

    def test_token_with_wrong_signature_returns_401(
        self, auth_client, jwt_token_generator, sample_job_data
    ):
        """Test that token with wrong signature returns 401."""
        wrong_token = jwt_token_generator.generate_invalid_token_wrong_key()

        response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {wrong_token}"},
        )

        assert response.status_code == 401
