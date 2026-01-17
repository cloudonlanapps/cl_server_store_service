"""
Tests for CRUD operations on entities.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from store.schemas import Item, PaginatedResponse


class TestEntityCRUD:
    """Test Create, Read, Update, Delete operations."""

    def test_create_collection(self, client: TestClient) -> None:
        """Test creating a collection without files."""
        response = client.post(
            "/entities/",
            data={
                "is_collection": "true",
                "label": "Test Collection",
                "description": "A test collection"
            }
        )

        assert response.status_code == 201
        item = Item.model_validate(response.json())
        assert item.id is not None
        assert item.is_collection is True
        assert item.label == "Test Collection"

    def test_get_entity_by_id(
        self, client: TestClient, sample_image: Path, clean_media_dir: Path
    ) -> None:
        """Test retrieving a specific entity by ID."""
        # Create entity
        with open(sample_image, "rb") as f:
            create_response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test Entity"}
            )

        created_item = Item.model_validate(create_response.json())
        assert created_item.id is not None
        entity_id = created_item.id

        # Get entity
        get_response = client.get(f"/entities/{entity_id}")
        assert get_response.status_code == 200
        item = Item.model_validate(get_response.json())
        assert item.id == entity_id
        assert item.label == "Test Entity"

    def test_get_all_entities(
        self, client: TestClient, sample_images: list[Path], clean_media_dir: Path
    ) -> None:
        """Test retrieving all entities."""
        # Create multiple entities
        for image_path in sample_images:
            with open(image_path, "rb") as f:
                client.post(
                    "/entities/",
                    files={"image": (image_path.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {image_path.name}"}
                )

        # Get all entities (request large page size to ensure we get all)
        response = client.get("/entities/?page_size=100")
        assert response.status_code == 200
        paginated = PaginatedResponse.model_validate(response.json())
        assert len(paginated.items) == len(sample_images)
        assert paginated.pagination.total_items == len(sample_images)

    def test_patch_entity(self, client: TestClient) -> None:
        """Test partially updating an entity."""
        # Create entity
        create_response = client.post(
            "/entities/",
            data={
                "is_collection": "true",
                "label": "Original Label",
                "description": "Original Description"
            }
        )
        created_item = Item.model_validate(create_response.json())
        assert created_item.id is not None
        entity_id = created_item.id

        # Patch entity (update only label)
        patch_response = client.patch(
            f"/entities/{entity_id}",
            data={"label": "Updated Label"}
        )

        assert patch_response.status_code == 200
        patched_item = Item.model_validate(patch_response.json())
        assert patched_item.label == "Updated Label"
        assert patched_item.description == "Original Description"  # Should remain unchanged
        assert isinstance(patched_item.updated_date, int)

    def test_patch_hierarchy(self, client: TestClient) -> None:
        """Test modifying entity hierarchy (parent_id)."""
        # Create parent collection
        parent_resp = client.post(
            "/entities/",
            data={"is_collection": "true", "label": "Parent Collection"}
        )
        parent_item = Item.model_validate(parent_resp.json())
        assert parent_item.id is not None
        parent_id = parent_item.id

        # Create child entity
        child_resp = client.post(
            "/entities/",
            data={"is_collection": "true", "label": "Child Entity"}
        )
        child_item = Item.model_validate(child_resp.json())
        assert child_item.id is not None
        child_id = child_item.id

        # 1. Move child to parent
        resp = client.patch(
            f"/entities/{child_id}",
            data={"parent_id": str(parent_id)}
        )
        assert resp.status_code == 200
        updated_child = Item.model_validate(resp.json())
        assert updated_child.parent_id == parent_id

        # 2. Remove child from parent (nullify parent_id)
        resp = client.patch(
            f"/entities/{child_id}",
            data={"parent_id": ""}
        )
        assert resp.status_code == 200
        updated_child = Item.model_validate(resp.json())
        assert updated_child.parent_id is None

    def test_delete_entity(
        self, client: TestClient, sample_image: Path, clean_media_dir: Path
    ) -> None:
        """Test hard deleting an entity."""
        # Create entity
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Delete Test"}
            )
        created_item = Item.model_validate(response.json())
        assert created_item.id is not None
        entity_id = created_item.id

        # Delete entity
        response = client.delete(f"/entities/{entity_id}")
        assert response.status_code == 204

        # Verify entity is GONE (Hard Delete)
        response = client.get(f"/entities/{entity_id}")
        assert response.status_code == 404

    def test_soft_delete_and_restore(
        self, client: TestClient, sample_image: Path, clean_media_dir: Path
    ) -> None:
        """Test soft delete and restore via PATCH."""
        # Create entity
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Soft Delete Test"}
            )
        created_item = Item.model_validate(response.json())
        assert created_item.id is not None
        entity_id = created_item.id

        # Soft Delete (PATCH is_deleted=True)
        response = client.patch(
            f"/entities/{entity_id}",
            data={"is_deleted": "true"}
        )
        assert response.status_code == 200
        deleted_item = Item.model_validate(response.json())
        assert deleted_item.is_deleted is True

        # Verify entity still exists but is marked deleted
        response = client.get(f"/entities/{entity_id}")
        assert response.status_code == 200
        get_item = Item.model_validate(response.json())
        assert get_item.is_deleted is True

        # Restore (PATCH is_deleted=False)
        response = client.patch(
            f"/entities/{entity_id}",
            data={"is_deleted": "false"}
        )
        assert response.status_code == 200
        restored_item = Item.model_validate(response.json())
        assert restored_item.is_deleted is False

        # Verify entity is restored
        response = client.get(f"/entities/{entity_id}")
        assert response.status_code == 200
        final_item = Item.model_validate(response.json())
        assert final_item.is_deleted is False

    def test_delete_all_entities(
        self, client: TestClient, sample_images: list[Path], clean_media_dir: Path
    ) -> None:
        """Test deleting all entities."""
        # Create multiple entities
        for image_path in sample_images:
            with open(image_path, "rb") as f:
                client.post(
                    "/entities/",
                    files={"image": (image_path.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {image_path.name}"}
                )

        # Delete all
        delete_response = client.delete("/entities/")
        assert delete_response.status_code == 204

        # Verify all deleted
        get_response = client.get("/entities/")
        assert get_response.status_code == 200
        paginated = PaginatedResponse.model_validate(get_response.json())
        assert len(paginated.items) == 0
        assert paginated.pagination.total_items == 0

    def test_get_nonexistent_entity(self, client: TestClient) -> None:
        """Test getting an entity that doesn't exist."""
        response = client.get("/entities/99999")
        assert response.status_code == 404

    def test_update_nonexistent_entity(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Test updating an entity that doesn't exist."""
        with open(sample_image, "rb") as f:
            response = client.put(
                "/entities/99999",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test"}
            )
        assert response.status_code == 404
