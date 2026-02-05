"""
Tests for entity versioning functionality using SQLAlchemy-Continuum.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from store.db_service.schemas import EntitySchema as Item





pytestmark = pytest.mark.integration
class TestEntityVersioning:
    """Test entity versioning with SQLAlchemy-Continuum."""

    def test_entity_creation_creates_version_1(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Test that creating an entity creates version 1."""
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Original Version",
                    "description": "This is version 1"
                }
            )

        assert response.status_code == 201
        item = Item.model_validate(response.json())
        assert item.id is not None
        entity_id = item.id

        # Query version 1 explicitly
        version_response = client.get(f"/entities/{entity_id}?version=1")
        assert version_response.status_code == 200
        version1 = Item.model_validate(version_response.json())
        assert version1.label == "Original Version"
        assert version1.description == "This is version 1"

    def test_entity_update_creates_new_version(
        self, client: TestClient, sample_images: list[Path]
    ) -> None:
        """Test that updating an entity creates a new version."""
        if len(sample_images) < 2:
            pytest.skip("Need at least 2 images for this test")

        image1, image2 = sample_images[0], sample_images[1]

        # Create entity (version 1)
        with open(image1, "rb") as f:
            create_response = client.post(
                "/entities/",
                files={"image": (image1.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Version 1",
                    "description": "First version"
                }
            )

        assert create_response.status_code == 201
        created_item = Item.model_validate(create_response.json())
        assert created_item.id is not None
        assert created_item.md5 is not None
        entity_id = created_item.id
        version1_md5 = created_item.md5

        # Update entity (creates version 2)
        with open(image2, "rb") as f:
            update_response = client.put(
                f"/entities/{entity_id}",
                files={"image": (image2.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Version 2",
                    "description": "Second version"
                }
            )

        assert update_response.status_code == 200
        updated_item = Item.model_validate(update_response.json())
        assert updated_item.md5 is not None
        version2_md5 = updated_item.md5

        # Verify version 1 still exists with original data
        v1_response = client.get(f"/entities/{entity_id}?version=1")
        assert v1_response.status_code == 200
        v1_item = Item.model_validate(v1_response.json())
        assert v1_item.label == "Version 1"
        assert v1_item.description == "First version"
        assert v1_item.md5 == version1_md5

        # Verify version 2 has new data
        v2_response = client.get(f"/entities/{entity_id}?version=2")
        assert v2_response.status_code == 200
        v2_item = Item.model_validate(v2_response.json())
        assert v2_item.label == "Version 2"
        assert v2_item.description == "Second version"
        assert v2_item.md5 == version2_md5
        assert v2_item.md5 != version1_md5

    def test_query_without_version_returns_latest(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Test that querying without version parameter returns the latest version."""
        # Create entity
        with open(sample_image, "rb") as f:
            create_response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Version 1"
                }
            )

        created_item = Item.model_validate(create_response.json())
        assert created_item.id is not None
        entity_id = created_item.id

        # Update entity (metadata only)
        update_response = client.put(
            f"/entities/{entity_id}",
            data={
                "is_collection": "false",
                "label": "Version 2 - Latest"
            }
        )

        assert update_response.status_code == 200

        # Query without version should return latest
        latest_response = client.get(f"/entities/{entity_id}")
        assert latest_response.status_code == 200
        latest_item = Item.model_validate(latest_response.json())
        assert latest_item.label == "Version 2 - Latest"

    def test_list_all_versions_of_entity(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Test listing all versions of an entity."""
        # Create entity
        with open(sample_image, "rb") as f:
            create_response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Version 1"
                }
            )

        created_item = Item.model_validate(create_response.json())
        assert created_item.id is not None
        entity_id = created_item.id

        # Update twice to create versions 2 and 3
        for i in range(2, 4):
            _ = client.put(
                f"/entities/{entity_id}",
                data={
                    "is_collection": "false",
                    "label": f"Version {i}"
                },
                files={}
            )

        # List all versions
        versions_response = client.get(f"/entities/{entity_id}/versions")
        assert versions_response.status_code == 200
        versions: list[dict[str, int | None]] = versions_response.json()

        # Should have 3 versions
        assert len(versions) >= 3

        # Verify version metadata
        for version_info in versions:
            assert "version" in version_info
            assert "transaction_id" in version_info or "updated_date" in version_info

    def test_patch_creates_new_version(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Test that PATCH operations also create new versions."""
        # Create entity
        with open(sample_image, "rb") as f:
            create_response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Original",
                    "description": "Original description"
                }
            )

        created_item = Item.model_validate(create_response.json())
        assert created_item.id is not None
        entity_id = created_item.id

        # Patch entity (should create version 2)
        patch_response = client.patch(
            f"/entities/{entity_id}",
            data={"label": "Patched Label"}
        )

        assert patch_response.status_code == 200

        # Verify version 1 has original label
        v1_response = client.get(f"/entities/{entity_id}?version=1")
        assert v1_response.status_code == 200
        v1_item = Item.model_validate(v1_response.json())
        assert v1_item.label == "Original"

        # Verify latest version has patched label
        latest_response = client.get(f"/entities/{entity_id}")
        assert latest_response.status_code == 200
        latest_item = Item.model_validate(latest_response.json())
        assert latest_item.label == "Patched Label"
        # Description should remain unchanged
        assert latest_item.description == "Original description"

    def test_query_nonexistent_version_returns_error(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Test that querying a non-existent version returns appropriate error."""
        # Create entity (only version 1 exists)
        with open(sample_image, "rb") as f:
            create_response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Test"
                }
            )

        created_item = Item.model_validate(create_response.json())
        assert created_item.id is not None
        entity_id = created_item.id

        # Try to query version 99 (doesn't exist)
        response = client.get(f"/entities/{entity_id}?version=99")
        assert response.status_code == 404
        error_data: dict[str, str] = response.json()
        assert "version" in error_data["detail"].lower()

    def test_collection_versioning(self, client: TestClient) -> None:
        """Test that collections are also versioned."""
        # Create collection
        create_response = client.post(
            "/entities/",
            data={
                "is_collection": "true",
                "label": "Collection V1",
                "description": "First version of collection"
            }
        )

        assert create_response.status_code == 201
        created_item = Item.model_validate(create_response.json())
        assert created_item.id is not None
        entity_id = created_item.id

        # Update collection
        update_response = client.put(
            f"/entities/{entity_id}",
            data={
                "is_collection": "true",
                "label": "Collection V2",
                "description": "Second version of collection"
            }
        )

        assert update_response.status_code == 200

        # Verify version 1
        v1_response = client.get(f"/entities/{entity_id}?version=1")
        assert v1_response.status_code == 200
        v1_item = Item.model_validate(v1_response.json())
        assert v1_item.label == "Collection V1"

        # Verify version 2
        v2_response = client.get(f"/entities/{entity_id}?version=2")
        assert v2_response.status_code == 200
        v2_item = Item.model_validate(v2_response.json())
        assert v2_item.label == "Collection V2"
