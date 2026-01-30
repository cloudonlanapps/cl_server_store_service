"""
Tests for CRUD operations on entities.
"""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from store.db_service.db_internals import Entity
from store.db_service.schemas import EntitySchema, PaginatedResponse
import pytest


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
        item = EntitySchema.model_validate(response.json())
        assert item.id is not None
        assert item.is_collection is True
        assert item.label == "Test Collection"

    def test_get_entity_by_id(self, client: TestClient, sample_image: Path) -> None:
        """Test retrieving a specific entity by ID."""
        # Create entity
        with open(sample_image, "rb") as f:
            create_response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test Entity"}
            )

        created_item = EntitySchema.model_validate(create_response.json())
        assert created_item.id is not None
        entity_id = created_item.id

        # Get entity
        get_response = client.get(f"/entities/{entity_id}")
        assert get_response.status_code == 200
        item = EntitySchema.model_validate(get_response.json())
        assert item.id == entity_id
        assert item.label == "Test Entity"
        # EntitySchema has explicit intelligence_data which is None by default
        assert item.intelligence_data is None

    def test_get_entity_with_intelligence_status(
        self, client: TestClient, sample_image: Path, test_db_session: Session
    ) -> None:
        """Test retrieving entity with populated intelligence status."""
        # Create entity
        with open(sample_image, "rb") as f:
            resp = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Intel Test"}
            )
        item = EntitySchema.model_validate(resp.json())
        entity_id = item.id

        # Manually create intelligence record
        entity_obj = test_db_session.get(Entity, entity_id)
        assert entity_obj is not None
        entity_obj.intelligence_data = {
            "overall_status": "completed",
            "active_processing_md5": item.md5 or "",
            "last_updated": 0,
            "inference_status": {
                "face_detection": "pending",
                "clip_embedding": "pending",
                "dino_embedding": "pending",
            }
        }
        test_db_session.commit()

        # Get entity
        get_response = client.get(f"/entities/{entity_id}")
        assert get_response.status_code == 200
        fetched_item = EntitySchema.model_validate(get_response.json())

        # Verify status
        # Note: We now return EntitySchema, which has intelligence_data dictionary/model
        # We need to access intelligence_data.overall_status
        assert fetched_item.intelligence_data is not None
        assert fetched_item.intelligence_data.overall_status == "completed"

    def test_get_all_entities(
        self,
        client: TestClient,
        sample_images: list[Path],
    ) -> None:
        """Test retrieving all entities."""
        # Create multiple entities with parent
        for image_path in sample_images:
            with open(image_path, "rb") as f:
                client.post(
                    "/entities/",
                    files={"image": (image_path.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {image_path.name}"},
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
        created_item = EntitySchema.model_validate(create_response.json())
        assert created_item.id is not None
        entity_id = created_item.id

        # Patch entity (update only label)
        patch_response = client.patch(
            f"/entities/{entity_id}",
            data={"label": "Updated Label"}
        )

        assert patch_response.status_code == 200
        patched_item = EntitySchema.model_validate(patch_response.json())
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
        parent_item = EntitySchema.model_validate(parent_resp.json())
        assert parent_item.id is not None
        parent_id = parent_item.id

        # Create child entity
        child_resp = client.post(
            "/entities/",
            data={"is_collection": "true", "label": "Child Entity"}
        )
        child_item = EntitySchema.model_validate(child_resp.json())
        assert child_item.id is not None
        child_id = child_item.id

        # 1. Move child to parent
        resp = client.patch(
            f"/entities/{child_id}",
            data={"parent_id": str(parent_id)}
        )
        assert resp.status_code == 200
        updated_child = EntitySchema.model_validate(resp.json())
        assert updated_child.parent_id == parent_id

        # 2. Try to remove child from parent (should fail for files, but this is a collection)
        # We are testing collection movement here
        resp = client.patch(
            f"/entities/{child_id}",
            data={"parent_id": ""}
        )
        assert resp.status_code == 200
        updated_child = EntitySchema.model_validate(resp.json())
        assert updated_child.parent_id is None

        # 3. Test circular hierarchy
        # Create hierarchy A -> B
        col_a_resp = client.post(
            "/entities/", data={"is_collection": "true", "label": "Collection A"}
        )
        col_a_id = col_a_resp.json()["id"]

        col_b_resp = client.post(
            "/entities/",
            data={
                "is_collection": "true",
                "label": "Collection B",
                "parent_id": str(col_a_id),
            },
        )
        col_b_id = col_b_resp.json()["id"]

        # Try to set A's parent to B (A -> B -> A)
        resp = client.patch(
            f"/entities/{col_a_id}",
            data={"parent_id": str(col_b_id)}
        )
        assert resp.status_code == 422
        assert "Circular hierarchy detected" in resp.text

    def test_create_non_collection_without_parent_succeeds(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Test that creating a file without a parent succeeds (orphan support)."""
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Orphan File"},
            )
        assert response.status_code == 201
        # assert "Non-collection entities must have a parent_id" in response.text

    @pytest.mark.skip(reason="delete not supported")
    def test_delete_collection_with_children(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Test that deleting a soft-deleted collection cascades to children."""
        # Create collection
        col_resp = client.post(
            "/entities/", data={"is_collection": "true", "label": "Parent"}
        )
        col_id = col_resp.json()["id"]

        # Add child file
        with open(sample_image, "rb") as f:
            child_resp = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Child File",
                    "parent_id": str(col_id),
                },
            )
        child_id = child_resp.json()["id"]
        assert client.get(f"/entities/{col_id}").status_code == 200

        # Soft-delete collection first
        soft_delete_resp = client.patch(f"/entities/{col_id}", data={"is_deleted": "true"})
        assert soft_delete_resp.status_code == 200

        # Hard delete collection (should cascade to children)
        resp = client.delete(f"/entities/{col_id}")
        assert resp.status_code == 204

        # Verify both collection and child are hard-deleted
        assert client.get(f"/entities/{col_id}").status_code == 404
        assert client.get(f"/entities/{child_id}").status_code == 404

    def test_indirect_deletion_detection(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Verify is_indirectly_deleted logic."""
        # Create hierarchy: Grandparent -> Parent -> Child (File)
        gp_resp = client.post(
            "/entities/", data={"is_collection": "true", "label": "Grandparent"}
        )
        gp_id = gp_resp.json()["id"]

        p_resp = client.post(
            "/entities/",
            data={
                "is_collection": "true",
                "label": "Parent",
                "parent_id": str(gp_id),
            },
        )
        p_id = p_resp.json()["id"]

        with open(sample_image, "rb") as f:
            c_resp = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Child",
                    "parent_id": str(p_id),
                },
            )
        c_id = c_resp.json()["id"]

        # Initial state: clear
        assert c_resp.json()["is_deleted"] is False
        assert c_resp.json()["is_indirectly_deleted"] is False

        # Soft delete Grandparent
        client.patch(f"/entities/{gp_id}", data={"is_deleted": "true"})

        # Check Child status
        c_get = client.get(f"/entities/{c_id}")
        assert c_get.json()["is_deleted"] is False  # Directly not deleted
        assert c_get.json()["is_indirectly_deleted"] is True  # Indirectly deleted

        # Restore Grandparent
        client.patch(f"/entities/{gp_id}", data={"is_deleted": "false"})

        # Check Child status
        c_get = client.get(f"/entities/{c_id}")
        assert c_get.json()["is_indirectly_deleted"] is False

    @pytest.mark.skip(reason="delete not supported")
    def test_delete_entity_hard_delete(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Test hard deleting an entity (requires soft-delete first)."""
        # Create parent collection
        parent_resp = client.post(
            "/entities/",
            data={
                "is_collection": "true",
                "label": "Parent Collection",
            },
        )
        parent_id = parent_resp.json()["id"]

        # Create entity with parent
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Delete Test",
                    "parent_id": str(parent_id),
                },
            )
        created_item = EntitySchema.model_validate(response.json())
        assert created_item.id is not None
        entity_id = created_item.id

        # Soft-delete entity first
        soft_delete_resp = client.patch(f"/entities/{entity_id}", data={"is_deleted": "true"})
        assert soft_delete_resp.status_code == 200

        # Hard delete entity
        response = client.delete(f"/entities/{entity_id}")
        assert response.status_code == 204

        # Verify entity is GONE (Hard Delete)
        response = client.get(f"/entities/{entity_id}")
        assert response.status_code == 404

    def test_soft_delete_and_restore(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Test soft delete and restore via PATCH."""
        # Create parent collection
        parent_resp = client.post(
            "/entities/",
            data={
                "is_collection": "true",
                "label": "Parent Collection",
            },
        )
        parent_id = parent_resp.json()["id"]

        # Create entity with parent
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Soft Delete Test",
                    "parent_id": str(parent_id),
                },
            )
        created_item = EntitySchema.model_validate(response.json())
        assert created_item.id is not None
        entity_id = created_item.id

        # Soft Delete (PATCH is_deleted=True)
        response = client.patch(
            f"/entities/{entity_id}",
            data={"is_deleted": "true"}
        )
        assert response.status_code == 200
        deleted_item = EntitySchema.model_validate(response.json())
        assert deleted_item.is_deleted is True

        # Verify entity still exists but is marked deleted
        response = client.get(f"/entities/{entity_id}")
        assert response.status_code == 200
        get_item = EntitySchema.model_validate(response.json())
        assert get_item.is_deleted is True

        # Restore (PATCH is_deleted=False)
        response = client.patch(
            f"/entities/{entity_id}",
            data={"is_deleted": "false"}
        )
        assert response.status_code == 200
        restored_item = EntitySchema.model_validate(response.json())
        assert restored_item.is_deleted is False

        # Verify entity is restored
        response = client.get(f"/entities/{entity_id}")
        assert response.status_code == 200
        final_item = EntitySchema.model_validate(response.json())
        assert final_item.is_deleted is False

    def test_get_nonexistent_entity(self, client: TestClient) -> None:
        """Test getting an entity that doesn't exist."""
        response = client.get("/entities/99999")
        assert response.status_code == 404

    def test_update_nonexistent_entity(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Test updating an entity that doesn't exist."""
        # Use a valid mock parent ID (the root collection) to avoid 422 on parent check
        with open(sample_image, "rb") as f:
            response = client.put(
                "/entities/99999",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test"},
            )
        # Should be 404 Not Found (Entity not found), not 422 Parent Invalid
        assert response.status_code == 404

    def test_max_depth_limit(self, client: TestClient) -> None:
        """Test that hierarchy depth is limited to 10 levels."""
        # Create root
        resp = client.post(
            "/entities/",
            data={"is_collection": "true", "label": "Level 1"},
        )
        assert resp.status_code == 201
        parent_id = resp.json()["id"]

        # Create 9 more levels (Total 10) - Should succeed
        for i in range(2, 11):
            resp = client.post(
                "/entities/",
                data={
                    "is_collection": "true",
                    "label": f"Level {i}",
                    "parent_id": str(parent_id),
                },
            )
            assert resp.status_code == 201
            parent_id = resp.json()["id"]

        # Try to create 11th level - Should fail
        resp = client.post(
            "/entities/",
            data={
                "is_collection": "true",
                "label": "Level 11",
                "parent_id": str(parent_id),
            },
        )
        assert resp.status_code == 422
        assert "Maximum hierarchy depth exceeded" in resp.text

    def test_get_entities_pagination(
        self, client: TestClient, sample_images: list[Path]
    ) -> None:
        """Test pagination for getting entities."""
        # Create multiple entities
        # Create parent collection
        parent_resp = client.post(
            "/entities/",
            data={
                "is_collection": "true",
                "label": "Parent Collection",
            },
        )
        parent_id = parent_resp.json()["id"]

        # Create multiple entities with parent
        for image_path in sample_images:
            with open(image_path, "rb") as f:
                client.post(
                    "/entities/",
                    files={"image": (image_path.name, f, "image/jpeg")},
                    data={
                        "is_collection": "false",
                        "label": f"Entity {image_path.name}",
                        "parent_id": str(parent_id),
                    },
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

    def test_filter_exclude_deleted(
        self, client: TestClient, sample_images: list[Path]
    ) -> None:
        """Verify exclude_deleted query parameter."""
        # Create parent collection
        parent_resp = client.post(
            "/entities/",
            data={"is_collection": "true", "label": "Parent"},
        )
        parent_id = parent_resp.json()["id"]

        # Create two entities
        # Ensure we have at least 2 images
        assert len(sample_images) >= 2
        for i in range(2):
            image = sample_images[i]
            with open(image, "rb") as f:
                client.post(
                    "/entities/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={
                        "is_collection": "false",
                        "label": f"Entity {i}",
                        "parent_id": str(parent_id),
                    },
                )

        # Get list
        resp = client.get("/entities/")
        items = resp.json()["items"]
        assert len(items) == 3  # Parent + 2 files
        entity_to_delete = items[1]["id"]  # Pick first file

        # Soft delete one
        client.patch(f"/entities/{entity_to_delete}", data={"is_deleted": "true"})

        # Get list (default: show everything)
        resp = client.get("/entities/")
        items = resp.json()["items"]
        assert len(items) == 3  # Parent + 2 files
        ids = [item["id"] for item in items]
        assert entity_to_delete in ids

        # Get list (exclude deleted)
        resp = client.get("/entities/?exclude_deleted=true")
        items = resp.json()["items"]
        assert len(items) == 2  # Parent + 1 file
        ids = [item["id"] for item in items]
        assert entity_to_delete not in ids

    @pytest.mark.skip(reason="delete not supported")
    def test_delete_without_soft_delete_fails(
        self, client: TestClient
    ) -> None:
        """Test that hard-delete without soft-delete first returns 422."""
        # Create entity
        response = client.post(
            "/entities/",
            data={"is_collection": "true", "label": "Test Collection"},
        )
        assert response.status_code == 201
        entity_id = response.json()["id"]

        # Try to hard-delete without soft-delete first
        response = client.delete(f"/entities/{entity_id}")
        assert response.status_code == 422
        assert "must be soft-deleted first" in response.text

    @pytest.mark.skip(reason="delete not supported")
    def test_cascade_deletion_soft_deletes_children(
        self, client: TestClient, sample_image: Path, test_db_session: Session
    ) -> None:
        """Test that deleting a collection soft-deletes children before hard-deleting them."""
        # Create collection
        response = client.post(
            "/entities/",
            data={"is_collection": "true", "label": "Parent Collection"},
        )
        assert response.status_code == 201
        parent_id = response.json()["id"]

        # Create child
        with sample_image.open("rb") as f:
            response = client.post(
                "/entities/",
                files={"image": ("test.jpg", f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Child Image",
                    "parent_id": str(parent_id),
                },
            )
        assert response.status_code == 201
        child_id = response.json()["id"]

        # Soft-delete parent
        response = client.patch(f"/entities/{parent_id}", data={"is_deleted": "true"})
        assert response.status_code == 200

        # Hard-delete parent (should cascade to child)
        response = client.delete(f"/entities/{parent_id}")
        assert response.status_code == 204

        # Verify both are hard-deleted
        assert client.get(f"/entities/{parent_id}").status_code == 404
        assert client.get(f"/entities/{child_id}").status_code == 404

    def test_soft_delete_marks_entity_deleted(
        self, client: TestClient, test_db_session: Session
    ) -> None:
        """Test that soft-delete marks entity as deleted and creates version record."""
        # Create entity
        response = client.post(
            "/entities/",
            data={"is_collection": "true", "label": "Test Collection"},
        )
        entity_id = response.json()["id"]

        # Verify entity exists and is not deleted
        entity = test_db_session.query(Entity).filter(Entity.id == entity_id).first()
        assert entity is not None
        assert entity.is_deleted is False

        # Get initial version count
        initial_version_count = len(entity.versions.all())

        # Soft-delete
        response = client.patch(f"/entities/{entity_id}", data={"is_deleted": "true"})
        assert response.status_code == 200

        # Verify entity still exists but is marked as deleted
        test_db_session.expire_all()
        entity = test_db_session.query(Entity).filter(Entity.id == entity_id).first()
        assert entity is not None
        assert entity.is_deleted is True

        # Verify a new version record was created
        final_version_count = len(entity.versions.all())
        assert final_version_count == initial_version_count + 1

        # Verify the latest version has is_deleted=True
        latest_version = entity.versions.all()[-1]
        assert latest_version.is_deleted is True

    @pytest.mark.skip(reason="delete not supported")
    def test_hard_delete_removes_entity_completely(
        self, client: TestClient, test_db_session: Session
    ) -> None:
        """Test that hard-delete removes entity from database."""
        # Create entity
        response = client.post(
            "/entities/",
            data={"is_collection": "true", "label": "Test Collection"},
        )
        entity_id = response.json()["id"]

        # Soft-delete
        response = client.patch(f"/entities/{entity_id}", data={"is_deleted": "true"})
        assert response.status_code == 200

        # Verify entity still exists in database
        entity = test_db_session.query(Entity).filter(Entity.id == entity_id).first()
        assert entity is not None
        assert entity.is_deleted is True

        # Hard-delete
        response = client.delete(f"/entities/{entity_id}")
        assert response.status_code == 204

        # Verify entity is completely removed from database
        test_db_session.expire_all()
        entity = test_db_session.query(Entity).filter(Entity.id == entity_id).first()
        assert entity is None
