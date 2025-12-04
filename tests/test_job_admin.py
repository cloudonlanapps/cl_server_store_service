"""
Tests for job admin endpoints.
Tests storage size tracking and cleanup functionality.
"""

import pytest


class TestStorageSizeEndpoint:
    """Test the storage size endpoint."""

    def test_get_storage_size_returns_correct_structure(self, auth_client, inference_admin_token):
        """Test that storage size endpoint returns correct data structure."""
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
        assert data["total_size"] >= 0
        assert data["job_count"] >= 0

    def test_storage_size_increases_after_job_creation(self, auth_client, inference_token, inference_admin_token, sample_job_data):
        """Test that storage size increases after creating a job."""
        # Get initial storage size
        initial_response = auth_client.get(
            "/jobs/admin/storage/size",
            headers={"Authorization": f"Bearer {inference_admin_token}"},
        )

        initial_count = initial_response.json()["job_count"]

        # Create a job
        auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        # Get storage size after job creation
        updated_response = auth_client.get(
            "/jobs/admin/storage/size",
            headers={"Authorization": f"Bearer {inference_admin_token}"},
        )

        updated_count = updated_response.json()["job_count"]

        # Job count should increase
        assert updated_count == initial_count + 1

    def test_storage_size_decreases_after_job_deletion(self, auth_client, inference_token, inference_admin_token, sample_job_data):
        """Test that storage size info reflects job deletion."""
        # Create a job
        create_response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        job_id = create_response.json()["job_id"]

        # Get storage size after job creation
        after_create = auth_client.get(
            "/jobs/admin/storage/size",
            headers={"Authorization": f"Bearer {inference_admin_token}"},
        )

        count_after_create = after_create.json()["job_count"]

        # Delete the job
        auth_client.delete(
            f"/jobs/{job_id}",
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        # Get storage size after job deletion
        after_delete = auth_client.get(
            "/jobs/admin/storage/size",
            headers={"Authorization": f"Bearer {inference_admin_token}"},
        )

        count_after_delete = after_delete.json()["job_count"]

        # Job count should decrease
        assert count_after_delete == count_after_create - 1


class TestCleanupEndpoint:
    """Test the cleanup old jobs endpoint."""

    def test_cleanup_with_valid_days_parameter(self, auth_client, inference_admin_token):
        """Test cleanup endpoint with valid days parameter."""
        response = auth_client.delete(
            "/jobs/admin/cleanup?days=7",
            headers={"Authorization": f"Bearer {inference_admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "deleted_count" in data
        assert "freed_space" in data
        assert isinstance(data["deleted_count"], int)
        assert isinstance(data["freed_space"], int)
        assert data["deleted_count"] >= 0
        assert data["freed_space"] >= 0

    def test_cleanup_with_default_days(self, auth_client, inference_admin_token):
        """Test cleanup endpoint with default days value."""
        response = auth_client.delete(
            "/jobs/admin/cleanup",
            headers={"Authorization": f"Bearer {inference_admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()

        # Should have default cleanup (probably 30 days)
        assert "deleted_count" in data
        assert "freed_space" in data

    def test_cleanup_with_zero_days_cleans_all(self, auth_client, inference_token, inference_admin_token, sample_job_data):
        """Test cleanup with days=0 parameter cleans all old jobs."""
        # Create a job
        auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        # Cleanup with days=0 should remove all jobs
        response = auth_client.delete(
            "/jobs/admin/cleanup?days=0",
            headers={"Authorization": f"Bearer {inference_admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()

        # Should have deleted the job
        assert data["deleted_count"] > 0

    def test_cleanup_returns_deleted_count(self, auth_client, inference_token, inference_admin_token, sample_job_data):
        """Test that cleanup returns the number of deleted jobs."""
        # Create multiple jobs
        created_jobs = []
        for i in range(3):
            response = auth_client.post(
                "/jobs/image_processing",
                data=sample_job_data,
                headers={"Authorization": f"Bearer {inference_token}"},
            )
            created_jobs.append(response.json()["job_id"])

        # Cleanup with days=0 to delete all
        cleanup_response = auth_client.delete(
            "/jobs/admin/cleanup?days=0",
            headers={"Authorization": f"Bearer {inference_admin_token}"},
        )

        assert cleanup_response.status_code == 200
        # Should have deleted at least the 3 jobs we created
        # (might be more if there were existing jobs)
        assert cleanup_response.json()["deleted_count"] >= 3

    def test_cleanup_preserves_recent_jobs(self, auth_client, inference_token, inference_admin_token, sample_job_data):
        """Test that cleanup with large days value preserves recent jobs."""
        # Create a job
        create_response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        job_id = create_response.json()["job_id"]

        # Cleanup with days=30 (recent jobs should be preserved)
        cleanup_response = auth_client.delete(
            "/jobs/admin/cleanup?days=30",
            headers={"Authorization": f"Bearer {inference_admin_token}"},
        )

        assert cleanup_response.status_code == 200

        # Verify the job still exists
        get_response = auth_client.get(
            f"/jobs/{job_id}",
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert get_response.status_code == 200


class TestAdminOnlyAccess:
    """Test that admin endpoints are restricted to admin users."""

    def test_non_admin_cannot_access_storage_size(self, auth_client, inference_token):
        """Test that non-admin users cannot access storage size endpoint."""
        response = auth_client.get(
            "/jobs/admin/storage/size",
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert response.status_code == 403

    def test_non_admin_cannot_cleanup(self, auth_client, inference_token):
        """Test that non-admin users cannot access cleanup endpoint."""
        response = auth_client.delete(
            "/jobs/admin/cleanup",
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert response.status_code == 403

    def test_read_permission_cannot_access_storage_size(self, auth_client, read_token):
        """Test that read-only users cannot access storage size endpoint."""
        response = auth_client.get(
            "/jobs/admin/storage/size",
            headers={"Authorization": f"Bearer {read_token}"},
        )

        assert response.status_code == 403

    def test_write_permission_cannot_access_storage_size(self, auth_client, write_token):
        """Test that write-only users cannot access storage size endpoint."""
        response = auth_client.get(
            "/jobs/admin/storage/size",
            headers={"Authorization": f"Bearer {write_token}"},
        )

        assert response.status_code == 403

    def test_admin_token_can_access_all_endpoints(self, auth_client, inference_admin_token):
        """Test that admin token can access all admin endpoints."""
        # Storage size
        storage_response = auth_client.get(
            "/jobs/admin/storage/size",
            headers={"Authorization": f"Bearer {inference_admin_token}"},
        )

        assert storage_response.status_code == 200

        # Cleanup
        cleanup_response = auth_client.delete(
            "/jobs/admin/cleanup",
            headers={"Authorization": f"Bearer {inference_admin_token}"},
        )

        assert cleanup_response.status_code == 200
