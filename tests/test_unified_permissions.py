"""
Tests for unified permission model across entity and job endpoints.
Tests interactions between entity (media_store_*) and job (ai_inference_support) permissions.
"""

import pytest


class TestEntityVsJobPermissions:
    """Test that entity and job endpoints have independent permissions."""

    def test_write_permission_allows_entity_but_not_job(
        self, auth_client, write_token, sample_image, sample_job_data
    ):
        """Test that write permission allows entity operations but not job operations."""
        # Should allow entity creation
        with open(sample_image, "rb") as f:
            entity_response = auth_client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test Entity"},
                headers={"Authorization": f"Bearer {write_token}"},
            )

        assert entity_response.status_code == 201

        # Should NOT allow job creation
        job_response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {write_token}"},
        )

        assert job_response.status_code == 403

    def test_inference_permission_allows_job_but_not_entity_write(
        self, auth_client, inference_token, sample_image, sample_job_data
    ):
        """Test that inference permission allows job operations but not entity write."""
        # Should allow job creation
        job_response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert job_response.status_code == 201

        # Should NOT allow entity creation
        with open(sample_image, "rb") as f:
            entity_response = auth_client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test Entity"},
                headers={"Authorization": f"Bearer {inference_token}"},
            )

        assert entity_response.status_code == 403

    def test_read_permission_allows_entity_read_but_not_write_or_job(
        self, auth_client, read_token, sample_job_data
    ):
        """Test that read permission allows entity read but not write or job operations."""
        # Should allow entity read (empty collection is ok)
        entity_list_response = auth_client.get(
            "/entities/",
            headers={"Authorization": f"Bearer {read_token}"},
        )

        assert entity_list_response.status_code == 200

        # Should NOT allow job creation
        job_response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {read_token}"},
        )

        assert job_response.status_code == 403

    def test_admin_permission_allows_both_entity_and_job(
        self, auth_client, admin_token, sample_image, sample_job_data
    ):
        """Test that admin permission allows both entity and job operations."""
        # Should allow entity creation
        with open(sample_image, "rb") as f:
            entity_response = auth_client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test Entity"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )

        assert entity_response.status_code == 201

        # Should allow job creation (admin has both permissions)
        job_response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert job_response.status_code == 201

        # Should allow storage size access
        storage_response = auth_client.get(
            "/jobs/admin/storage/size",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert storage_response.status_code == 200


class TestInferenceAdminPermissions:
    """Test inference admin token permissions."""

    def test_inference_admin_can_access_job_endpoints(
        self, auth_client, inference_admin_token, sample_job_data
    ):
        """Test that inference admin can access job creation endpoint."""
        response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {inference_admin_token}"},
        )

        assert response.status_code == 201

    def test_inference_admin_can_access_admin_endpoints(
        self, auth_client, inference_admin_token
    ):
        """Test that inference admin can access admin endpoints."""
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

    def test_inference_admin_cannot_write_entities(
        self, auth_client, inference_admin_token, sample_image
    ):
        """Test that inference admin CAN write entities (admin bypasses permission checks)."""
        with open(sample_image, "rb") as f:
            response = auth_client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test Entity"},
                headers={"Authorization": f"Bearer {inference_admin_token}"},
            )

        assert response.status_code == 201  # Admin bypasses permission checks


class TestCombinedOperations:
    """Test combined operations across entity and job endpoints."""

    def test_entity_and_job_operations_are_independent(
        self, auth_client, write_token, inference_token, sample_image, sample_job_data
    ):
        """Test that entity and job operations don't interfere with each other."""
        # Create entity with write token
        with open(sample_image, "rb") as f:
            entity_response = auth_client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test Entity"},
                headers={"Authorization": f"Bearer {write_token}"},
            )

        entity_id = entity_response.json()["id"]

        # Create job with inference token
        job_response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        job_id = job_response.json()["job_id"]

        # Verify entity can still be accessed with write token
        entity_get = auth_client.get(
            f"/entities/{entity_id}",
            headers={"Authorization": f"Bearer {write_token}"},
        )

        assert entity_get.status_code == 200

        # Verify job can still be accessed with inference token
        job_get = auth_client.get(
            f"/jobs/{job_id}",
            headers={"Authorization": f"Bearer {inference_token}"},
        )

        assert job_get.status_code == 200

    def test_demo_mode_allows_all_operations(self, client, sample_image):
        """Test that demo mode (bypassed auth) allows all operations."""
        # Demo client has full permissions

        # Create entity
        with open(sample_image, "rb") as f:
            entity_response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Demo Entity"},
            )

        assert entity_response.status_code == 201

        # Create job
        job_data = {
            "task_type": "image_processing",
            "priority": 5,
            "external_files": "[]",
        }

        job_response = client.post(
            "/jobs/image_processing",
            data=job_data,
        )

        assert job_response.status_code == 201

        # Access admin endpoint
        storage_response = client.get("/jobs/admin/storage/size")

        assert storage_response.status_code == 200


class TestPermissionHierarchy:
    """Test permission hierarchy and combinations."""

    def test_multiple_permissions_cumulative(
        self, jwt_token_generator, auth_client, sample_image, sample_job_data
    ):
        """Test that user with multiple permissions can access all endpoints."""
        # Create token with both read and write permissions
        multi_token = jwt_token_generator.generate_token(
            sub="multi_user",
            permissions=[
                "media_store_read",
                "media_store_write",
                "ai_inference_support",
            ],
            is_admin=False,
        )

        # Should allow entity write
        with open(sample_image, "rb") as f:
            entity_response = auth_client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Multi Entity"},
                headers={"Authorization": f"Bearer {multi_token}"},
            )

        assert entity_response.status_code == 201

        # Should allow job creation
        job_response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {multi_token}"},
        )

        assert job_response.status_code == 201

        # Should NOT allow admin operations (no admin status)
        admin_response = auth_client.get(
            "/jobs/admin/storage/size",
            headers={"Authorization": f"Bearer {multi_token}"},
        )

        assert admin_response.status_code == 403

    def test_admin_overrides_all_restrictions(
        self, jwt_token_generator, auth_client, sample_image, sample_job_data
    ):
        """Test that admin flag overrides all permission requirements."""
        # Create token with minimal permissions but admin=True
        admin_token = jwt_token_generator.generate_token(
            sub="minimal_admin",
            permissions=["media_store_read"],  # Only read permission
            is_admin=True,
        )

        # Should allow job creation (admin override)
        job_response = auth_client.post(
            "/jobs/image_processing",
            data=sample_job_data,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert job_response.status_code == 201

        # Should allow entity write (admin override)
        with open(sample_image, "rb") as f:
            entity_response = auth_client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Admin Entity"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )

        assert entity_response.status_code == 201

        # Should allow admin operations
        admin_response = auth_client.get(
            "/jobs/admin/storage/size",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert admin_response.status_code == 200
