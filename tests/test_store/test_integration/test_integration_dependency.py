"""Integration tests that verify FastAPI dependency injection works correctly.

These tests use the standard integration test client from conftest.py.
They verify that the dependency injection works correctly with real services.
"""


from store.db_service.schemas import EntitySchema
import pytest



# Use the standard client fixture from conftest.py which already tests real dependency injection



pytestmark = pytest.mark.integration
class TestDependencyInjection:
    """Tests that verify get_db() properly yields a database session."""

    def test_get_db_yields_session_not_generator(self, client):
        """Critical: Verify get_db() yields a Session, not a generator object.

        This test would FAIL with the broken 'return get_db_session()' code
        because FastAPI would inject a generator object instead of a Session.

        With the fixed 'yield from get_db_session()' code, FastAPI properly
        recognizes the generator and injects the yielded Session object.

        If get_db() is broken, this will return 500 with:
        AttributeError: 'generator' object has no attribute 'query'
        """
        

        # Create a collection entity (doesn't require file upload)
        response = client.post(
            "/entities/", data={"is_collection": "true", "label": "Test Collection"}
        )

        # If get_db() is broken, this will return 500
        assert response.status_code == 201, (
            f"Entity creation failed: {response.json() if response.status_code != 500 else response.text}"
        )
        item = EntitySchema.model_validate(response.json())
        assert item.label == "Test Collection"
        assert item.is_collection is True

    def test_root_endpoint_works(self, client):
        """Test root endpoint with real dependency injection."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"

    def test_entity_retrieval_works(self, client):
        """Test entity retrieval with real dependency injection."""
        

        # Create entity first
        create_response = client.post(
            "/entities/", data={"is_collection": "true", "label": "Test Entity"}
        )
        assert create_response.status_code == 201
        created_item = EntitySchema.model_validate(create_response.json())
        entity_id = created_item.id

        # Retrieve entity
        get_response = client.get(f"/entities/{entity_id}")
        assert get_response.status_code == 200
        retrieved_item = EntitySchema.model_validate(get_response.json())
        assert retrieved_item.id == entity_id
        assert retrieved_item.label == "Test Entity"


class TestEntityOperations:
    """Tests for entity CRUD operations with real dependencies."""

    def test_create_and_update_entity(self, client):
        """Test creating and updating entities through real get_db()."""
        # Create entity
        create_response = client.post(
            "/entities/",
            data={
                "is_collection": "true",
                "label": "Original Name",
                "description": "Original description",
            },
        )
        assert create_response.status_code == 201
        created_item = EntitySchema.model_validate(create_response.json())
        entity_id = created_item.id

        # Update entity
        update_response = client.patch(
            f"/entities/{entity_id}",
            data={"label": "Updated Name", "description": "Updated description"},
        )
        assert update_response.status_code == 200
        updated_item = EntitySchema.model_validate(update_response.json())
        assert updated_item.label == "Updated Name"
        assert updated_item.description == "Updated description"

    def test_create_multiple_entities(self, client):
        """Test creating multiple entities to verify session cleanup."""
        entity_ids = []

        for i in range(5):
            response = client.post(
                "/entities/", data={"is_collection": "true", "label": f"Entity {i}"}
            )
            assert response.status_code == 201
            created_item = EntitySchema.model_validate(response.json())
            entity_ids.append(created_item.id)

        # Verify all entities exist
        for entity_id in entity_ids:
            response = client.get(f"/entities/{entity_id}")
            assert response.status_code == 200

    def test_delete_entity(self, client):
        """Test entity deletion with real dependency injection."""
        # Create entity
        create_response = client.post(
            "/entities/", data={"is_collection": "true", "label": "To Be Deleted"}
        )
        assert create_response.status_code == 201
        created_item = EntitySchema.model_validate(create_response.json())
        entity_id = created_item.id

        # Soft-delete entity first
        soft_delete_response = client.patch(f"/entities/{entity_id}", data={"is_deleted": "true"})
        assert soft_delete_response.status_code == 200

        # Hard delete entity
        delete_response = client.delete(f"/entities/{entity_id}")
        assert delete_response.status_code == 204

        # Verify deletion
        get_response = client.get(f"/entities/{entity_id}")
        assert get_response.status_code == 404


class TestFileUpload:
    """Tests for file upload operations with real dependencies."""

    def test_file_upload_with_real_dependency(self, client):
        """Test file upload endpoint with real get_db()."""
        # Create a simple test image (1x1 PNG)
        png_data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
            b"\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        # Create entity with file
        create_response = client.post(
            "/entities/",
            data={"is_collection": "false", "label": "Entity with File"},
            files={"image": ("test.png", png_data, "image/png")},
        )
        assert create_response.status_code == 201
        created_item = EntitySchema.model_validate(create_response.json())
        assert created_item.file_path is not None
        assert created_item.mime_type == "image/png"


class TestMultipleSequentialRequests:
    """Test that database sessions are properly managed across requests."""

    def test_sequential_entity_operations(self, client):
        """Verify sessions are properly created and cleaned up."""
        entity_ids = []

        for i in range(10):
            response = client.post(
                "/entities/", data={"is_collection": "true", "label": f"Seq {i}"}
            )
            assert response.status_code == 201
            created_item = EntitySchema.model_validate(response.json())
            entity_ids.append(created_item.id)

        # Verify all entities are accessible
        for entity_id in entity_ids:
            response = client.get(f"/entities/{entity_id}")
            assert response.status_code == 200

    def test_mixed_operations_sequential(self, client):
        """Test mixed create/read/update/delete operations."""
        # Create
        create_resp = client.post(
            "/entities/", data={"is_collection": "true", "label": "Mixed Test"}
        )
        assert create_resp.status_code == 201
        created_item = EntitySchema.model_validate(create_resp.json())
        entity_id = created_item.id

        # Read
        read_resp = client.get(f"/entities/{entity_id}")
        assert read_resp.status_code == 200

        # Update
        update_resp = client.patch(
            f"/entities/{entity_id}", data={"label": "Updated Mixed Test"}
        )
        assert update_resp.status_code == 200

        # Read again
        read_resp2 = client.get(f"/entities/{entity_id}")
        assert read_resp2.status_code == 200
        updated_item = EntitySchema.model_validate(read_resp2.json())
        assert updated_item.label == "Updated Mixed Test"

        # Soft-delete first
        soft_delete_resp = client.patch(f"/entities/{entity_id}", data={"is_deleted": "true"})
        assert soft_delete_resp.status_code == 200

        # Hard delete
        delete_resp = client.delete(f"/entities/{entity_id}")
        assert delete_resp.status_code == 204

        # Verify deletion
        final_read = client.get(f"/entities/{entity_id}")
        assert final_read.status_code == 404
