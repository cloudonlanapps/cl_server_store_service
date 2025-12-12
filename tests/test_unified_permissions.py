"""
Tests for unified permission model across entity and job endpoints.
Tests interactions between entity (media_store_*) and job (ai_inference_support) permissions.
"""

from io import BytesIO
import pytest
from PIL import Image


def create_test_image():
    """Create a test image as BytesIO for job creation."""
    img = Image.new('RGB', (100, 100), color='red')
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes


def create_job_via_plugin(client, token=None, include_auth=True):
    """Helper to create a job using the plugin API.
    
    Args:
        client: Test client
        token: JWT token (optional if include_auth is False)
        include_auth: Whether to include authorization header
    
    Returns:
        tuple: (response, job_id or None)
    """
    img_bytes = create_test_image()
    headers = {"Authorization": f"Bearer {token}"} if include_auth and token else {}
    response = client.post(
        "/compute/jobs/image_resize",
        data={
            "width": "50",
            "height": "50",
            "maintain_aspect_ratio": "false",
            "priority": "5",
        },
        files={"file": ("test.png", img_bytes, "image/png")},
        headers=headers,
    )
    job_id = response.json().get("job_id") if response.status_code == 200 else None
    return response, job_id


class TestEntityVsJobPermissions:
    """Test that entity and job endpoints have independent permissions."""

    def test_write_permission_allows_entity_but_not_job(
        self, auth_client, write_token, sample_image
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

        # Should NOT allow job creation (missing ai_inference_support permission)
        response, _ = create_job_via_plugin(auth_client, write_token)
        assert response.status_code == 403

    def test_inference_permission_allows_job_but_not_entity_write(
        self, auth_client, inference_token, sample_image
    ):
        """Test that inference permission allows job operations but not entity write."""
        # Should allow job creation
        response, _ = create_job_via_plugin(auth_client, inference_token)
        assert response.status_code == 200

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
        self, auth_client, read_token
    ):
        """Test that read permission allows entity read but not write or job operations."""
        # Should allow entity read (empty collection is ok)
        entity_list_response = auth_client.get(
            "/entities/",
            headers={"Authorization": f"Bearer {read_token}"},
        )

        assert entity_list_response.status_code == 200

        # Should NOT allow job creation
        response, _ = create_job_via_plugin(auth_client, read_token)
        assert response.status_code == 403

    def test_admin_permission_allows_both_entity_and_job(
        self, auth_client, admin_token, sample_image
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

        # Should allow job creation (admin has all permissions)
        response, _ = create_job_via_plugin(auth_client, admin_token)
        assert response.status_code == 200

        # Should allow storage size access
        storage_response = auth_client.get(
            "/admin/compute/jobs/storage/size",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert storage_response.status_code == 200


class TestInferenceAdminPermissions:
    """Test inference admin token permissions."""

    def test_inference_admin_can_access_job_endpoints(
        self, auth_client, inference_admin_token
    ):
        """Test that inference admin can access job creation endpoint."""
        response, _ = create_job_via_plugin(auth_client, inference_admin_token)
        assert response.status_code == 200

    def test_inference_admin_can_access_admin_endpoints(
        self, auth_client, inference_admin_token
    ):
        """Test that inference admin can access admin endpoints."""
        # Storage size
        storage_response = auth_client.get(
            "/admin/compute/jobs/storage/size",
            headers={"Authorization": f"Bearer {inference_admin_token}"},
        )

        assert storage_response.status_code == 200

        # Cleanup
        cleanup_response = auth_client.delete(
            "/admin/compute/jobs/cleanup",
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


class TestPermissionHierarchy:
    """Test permission hierarchy and combinations."""

    def test_multiple_permissions_with_write_and_inference(
        self, write_token, inference_token, auth_client, sample_image
    ):
        """Test that users with write and inference permissions can access respective endpoints."""
        # Write permission should allow entity write
        with open(sample_image, "rb") as f:
            entity_response = auth_client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Write Entity"},
                headers={"Authorization": f"Bearer {write_token}"},
            )

        assert entity_response.status_code == 201

        # Inference permission should allow job creation
        response, _ = create_job_via_plugin(auth_client, inference_token)
        assert response.status_code == 200

        # Write permission should NOT allow admin operations
        admin_response = auth_client.get(
            "/admin/compute/jobs/storage/size",
            headers={"Authorization": f"Bearer {write_token}"},
        )

        assert admin_response.status_code == 403

    def test_admin_overrides_all_restrictions(
        self, admin_token, auth_client, sample_image
    ):
        """Test that admin flag overrides all permission requirements."""
        # Should allow job creation (admin override)
        response, _ = create_job_via_plugin(auth_client, admin_token)
        assert response.status_code == 200

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
            "/admin/compute/jobs/storage/size",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert admin_response.status_code == 200


class TestCombinedOperations:
    """Test combined operations across entity and job endpoints."""

    def test_entity_and_job_operations_are_independent(
        self, auth_client, write_token, inference_token, sample_image
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
        response, job_id = create_job_via_plugin(auth_client, inference_token)
        assert response.status_code == 200
        assert job_id is not None

        # Verify entity can still be accessed with write token
        entity_get = auth_client.get(
            f"/entities/{entity_id}",
            headers={"Authorization": f"Bearer {write_token}"},
        )

        assert entity_get.status_code == 200

        # Verify job can still be accessed with inference token
        job_get = auth_client.get(
            f"/compute/jobs/{job_id}",
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

        # Create job (demo mode doesn't require token)
        img_bytes = create_test_image()
        job_response = client.post(
            "/compute/jobs/image_resize",
            data={
                "width": "50",
                "height": "50",
                "maintain_aspect_ratio": "false",
                "priority": "5",
            },
            files={"file": ("test.png", img_bytes, "image/png")},
        )

        assert job_response.status_code == 200

        # Access admin endpoint
        storage_response = client.get("/admin/compute/jobs/storage/size")

        assert storage_response.status_code == 200
