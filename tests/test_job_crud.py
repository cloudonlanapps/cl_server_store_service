"""
Tests for job CRUD operations.
Tests basic creation, retrieval, and deletion of jobs.
"""

import json
import pytest


class TestJobCreation:
    """Test job creation functionality."""

    def test_create_job_with_valid_data(self, client, sample_job_data):
        """Test creating a job with valid data."""
        response = client.post(
            "/compute/jobs/image_processing",
            data=sample_job_data,
        )

        assert response.status_code == 201
        data = response.json()

        # Verify job was created with correct fields
        assert data["task_type"] == "image_processing"
        assert data["status"] == "queued"
        assert data["priority"] == 5
        assert data["progress"] == 0
        assert "job_id" in data
        assert data["job_id"] is not None
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_job_with_external_files(
        self, auth_client, inference_token, sample_job_data_with_external
    ):
        """Test creating a job with external file references."""
        response = auth_client.post(
            "/compute/jobs/video_analysis",
            data=sample_job_data_with_external,
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert response.status_code == 201
        data = response.json()

        assert data["task_type"] == "video_analysis"
        assert data["priority"] == 3
        # External files should be stored
        assert data["external_files"] is not None

    def test_create_high_priority_job(
        self, auth_client, inference_token, sample_job_data_high_priority
    ):
        """Test creating a high-priority job."""
        response = auth_client.post(
            "/compute/jobs/transcoding",
            data=sample_job_data_high_priority,
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert response.status_code == 201
        data = response.json()

        assert data["task_type"] == "transcoding"
        assert data["priority"] == 10

    def test_create_job_without_authentication_fails(
        self, auth_client, sample_job_data
    ):
        """Test that creating a job without authentication fails."""
        response = auth_client.post(
            "/compute/jobs/image_processing",
            data=sample_job_data,
        )

        assert response.status_code == 401

    def test_create_job_with_wrong_permission_fails(
        self, auth_client, write_token, sample_job_data
    ):
        """Test that creating a job with wrong permission fails."""
        response = auth_client.post(
            "/compute/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {write_token}"},
        )

        assert response.status_code == 403

    def test_create_job_with_invalid_priority_fails(self, auth_client, inference_token):
        """Test that creating a job with invalid priority fails."""
        invalid_data = {
            "task_type": "image_processing",
            "priority": 15,  # Invalid: max is 10
            "external_files": "[]",
        }

        response = auth_client.post(
            "/compute/jobs/image_processing",
            data=invalid_data,
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert response.status_code == 400

    def test_create_job_with_invalid_json_external_files_fails(
        self, auth_client, inference_token
    ):
        """Test that creating a job with invalid JSON in external_files fails."""
        invalid_data = {
            "task_type": "image_processing",
            "priority": 5,
            "external_files": "not valid json",
        }

        response = auth_client.post(
            "/compute/jobs/image_processing",
            data=invalid_data,
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert response.status_code == 400


class TestJobRetrieval:
    """Test job retrieval functionality."""

    def test_get_job_by_id(self, auth_client, inference_token, sample_job_data):
        """Test retrieving a job by ID."""
        # Create a job
        create_response = auth_client.post(
            "/compute/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert create_response.status_code == 201
        created_job = create_response.json()
        job_id = created_job["job_id"]

        # Retrieve the job
        get_response = auth_client.get(
            f"/compute/jobs/{job_id}",
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert get_response.status_code == 200
        job = get_response.json()

        assert job["job_id"] == job_id
        assert job["task_type"] == "image_processing"
        assert job["status"] == "queued"

    def test_get_nonexistent_job_fails(self, auth_client, inference_token):
        """Test retrieving a nonexistent job returns 404."""
        response = auth_client.get(
            "/compute/jobs/nonexistent-job-id",
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert response.status_code == 404

    def test_get_job_without_authentication_fails(self, auth_client):
        """Test retrieving a job without authentication fails."""
        response = auth_client.get("/compute/jobs/some-job-id")

        assert response.status_code == 401

    def test_get_job_with_wrong_permission_fails(self, auth_client, write_token):
        """Test retrieving a job with wrong permission fails."""
        response = auth_client.get(
            "/compute/jobs/some-job-id",
            headers={"Authorization": f"Bearer {write_token}"},
        )

        assert response.status_code == 403


class TestJobDeletion:
    """Test job deletion functionality."""

    def test_delete_job_by_id(self, auth_client, inference_token, sample_job_data):
        """Test deleting a job by ID."""
        # Create a job
        create_response = auth_client.post(
            "/compute/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        job_id = create_response.json()["job_id"]

        # Delete the job
        delete_response = auth_client.delete(
            f"/compute/jobs/{job_id}",
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert delete_response.status_code == 204

        # Verify job is deleted
        get_response = auth_client.get(
            f"/compute/jobs/{job_id}",
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert get_response.status_code == 404

    def test_delete_nonexistent_job_fails(self, auth_client, inference_token):
        """Test deleting a nonexistent job returns 404."""
        response = auth_client.delete(
            "/compute/jobs/nonexistent-job-id",
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert response.status_code == 404

    def test_delete_job_without_authentication_fails(self, auth_client):
        """Test deleting a job without authentication fails."""
        response = auth_client.delete("/compute/jobs/some-job-id")

        assert response.status_code == 401

    def test_delete_job_with_wrong_permission_fails(self, auth_client, write_token):
        """Test deleting a job with wrong permission fails."""
        response = auth_client.delete(
            "/compute/jobs/some-job-id",
            headers={"Authorization": f"Bearer {write_token}"},
        )

        assert response.status_code == 403


class TestJobLifecycle:
    """Test the complete lifecycle of a job."""

    def test_job_lifecycle_create_retrieve_delete(
        self, auth_client, inference_token, sample_job_data
    ):
        """Test creating, retrieving, and deleting a job."""
        # Create
        create_response = auth_client.post(
            "/compute/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert create_response.status_code == 201
        job_id = create_response.json()["job_id"]

        # Retrieve
        get_response = auth_client.get(
            f"/compute/jobs/{job_id}",
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert get_response.status_code == 200
        retrieved_job = get_response.json()
        assert retrieved_job["job_id"] == job_id
        assert retrieved_job["status"] == "queued"

        # Delete
        delete_response = auth_client.delete(
            f"/compute/jobs/{job_id}",
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert delete_response.status_code == 204

        # Verify deletion
        get_after_delete = auth_client.get(
            f"/compute/jobs/{job_id}",
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert get_after_delete.status_code == 404

    def test_create_multiple_jobs(self, auth_client, inference_token, sample_job_data):
        """Test creating multiple jobs."""
        job_ids = []

        for i in range(3):
            response = auth_client.post(
                "/compute/jobs/image_processing",
                data=sample_job_data,
                headers={"Authorization": f"Bearer {inference_token}"},
            )

            assert response.status_code == 201
            job_ids.append(response.json()["job_id"])

        # Verify all jobs can be retrieved
        for job_id in job_ids:
            response = auth_client.get(
                f"/compute/jobs/{job_id}",
                headers={"Authorization": f"Bearer {inference_token}"},
            )

            assert response.status_code == 200
