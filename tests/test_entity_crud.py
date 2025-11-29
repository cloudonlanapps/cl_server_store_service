"""
Tests for CRUD operations on entities.
"""


class TestEntityCRUD:
    """Test Create, Read, Update, Delete operations."""
    
    def test_create_collection(self, client):
        """Test creating a collection without files."""
        response = client.post(
            "/entity/",
            data={
                "is_collection": "true",
                "label": "Test Collection",
                "description": "A test collection"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["id"] is not None
        assert data["is_collection"] is True
        assert data["label"] == "Test Collection"
    
    def test_get_entity_by_id(self, client, sample_image, clean_media_dir):
        """Test retrieving a specific entity by ID."""
        # Create entity
        with open(sample_image, "rb") as f:
            create_response = client.post(
                "/entity/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test Entity"}
            )
        
        entity_id = create_response.json()["id"]
        
        # Get entity
        get_response = client.get(f"/entity/{entity_id}")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["id"] == entity_id
        assert data["label"] == "Test Entity"
    
    def test_get_all_entities(self, client, sample_images, clean_media_dir):
        """Test retrieving all entities."""
        # Create multiple entities
        for image_path in sample_images:
            with open(image_path, "rb") as f:
                client.post(
                    "/entity/",
                    files={"image": (image_path.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {image_path.name}"}
                )
        
        # Get all entities (request large page size to ensure we get all)
        response = client.get("/entity/?page_size=100")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "pagination" in data
        assert len(data["items"]) == len(sample_images)
        assert data["pagination"]["total_items"] == len(sample_images)
    
    def test_patch_entity(self, client):
        """Test partially updating an entity."""
        # Create entity
        create_response = client.post(
            "/entity/",
            data={
                "is_collection": "true",
                "label": "Original Label",
                "description": "Original Description"
            }
        )
        entity_id = create_response.json()["id"]
        
        # Patch entity (update only label)
        patch_response = client.patch(
            f"/entity/{entity_id}",
            json={"body": {"label": "Updated Label"}}
        )
        
        assert patch_response.status_code == 200
        data = patch_response.json()
        assert data["label"] == "Updated Label"
        assert data["description"] == "Original Description"  # Should remain unchanged
        assert isinstance(data["updated_date"], int)

    def test_patch_hierarchy(self, client):
        """Test modifying entity hierarchy (parent_id)."""
        # Create parent collection
        parent_resp = client.post(
            "/entity/",
            data={"is_collection": "true", "label": "Parent Collection"}
        )
        parent_id = parent_resp.json()["id"]
        
        # Create child entity
        child_resp = client.post(
            "/entity/",
            data={"is_collection": "true", "label": "Child Entity"}
        )
        child_id = child_resp.json()["id"]
        
        # 1. Move child to parent
        resp = client.patch(
            f"/entity/{child_id}",
            json={"body": {"parent_id": parent_id}}
        )
        assert resp.status_code == 200
        assert resp.json()["parent_id"] == parent_id
        
        # 2. Remove child from parent (nullify parent_id)
        resp = client.patch(
            f"/entity/{child_id}",
            json={"body": {"parent_id": None}}
        )
        assert resp.status_code == 200
        assert resp.json()["parent_id"] is None
    
    def test_delete_entity(self, client, sample_image, clean_media_dir):
        """Test hard deleting an entity."""
        # Create entity
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entity/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Delete Test"}
            )
        entity_id = response.json()["id"]
        
        # Delete entity
        response = client.delete(f"/entity/{entity_id}")
        assert response.status_code == 200
        
        # Verify entity is GONE (Hard Delete)
        response = client.get(f"/entity/{entity_id}")
        assert response.status_code == 404

    def test_soft_delete_and_restore(self, client, sample_image, clean_media_dir):
        """Test soft delete and restore via PATCH."""
        # Create entity
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entity/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Soft Delete Test"}
            )
        entity_id = response.json()["id"]
        
        # Soft Delete (PATCH is_deleted=True)
        response = client.patch(
            f"/entity/{entity_id}",
            json={"body": {"is_deleted": True}}
        )
        assert response.status_code == 200
        assert response.json()["is_deleted"] is True
        
        # Verify entity still exists but is marked deleted
        response = client.get(f"/entity/{entity_id}")
        assert response.status_code == 200
        assert response.json()["is_deleted"] is True
        
        # Restore (PATCH is_deleted=False)
        response = client.patch(
            f"/entity/{entity_id}",
            json={"body": {"is_deleted": False}}
        )
        assert response.status_code == 200
        assert response.json()["is_deleted"] is False
        
        # Verify entity is restored
        response = client.get(f"/entity/{entity_id}")
        assert response.status_code == 200
        assert response.json()["is_deleted"] is False
    
    def test_delete_all_entities(self, client, sample_images, clean_media_dir):
        """Test deleting all entities."""
        # Create multiple entities
        for image_path in sample_images:
            with open(image_path, "rb") as f:
                client.post(
                    "/entity/",
                    files={"image": (image_path.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {image_path.name}"}
                )
        
        # Delete all
        delete_response = client.delete("/entity/")
        assert delete_response.status_code == 200
        
        # Verify all deleted
        get_response = client.get("/entity/")
        assert get_response.status_code == 200
        data = get_response.json()
        assert len(data["items"]) == 0
        assert data["pagination"]["total_items"] == 0
    
    def test_get_nonexistent_entity(self, client):
        """Test getting an entity that doesn't exist."""
        response = client.get("/entity/99999")
        assert response.status_code == 404
    
    def test_update_nonexistent_entity(self, client, sample_image):
        """Test updating an entity that doesn't exist."""
        with open(sample_image, "rb") as f:
            response = client.put(
                "/entity/99999",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test"}
            )
        assert response.status_code == 404
