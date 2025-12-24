"""Integration tests that verify FastAPI dependency injection works correctly.

These tests use the REAL get_db() function without overrides to ensure
the production dependency injection path works correctly.

Key difference from other tests:
- Other tests override get_db() with a test implementation
- These tests configure the database via environment variables
- This ensures the ACTUAL get_db() function is tested

NOTE: These tests should be run separately from the main test suite due to
module reloading. Run with: pytest tests/test_integration_dependency.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

# Mark all tests in this module to be run separately
pytestmark = pytest.mark.integration


@pytest.fixture(scope="function")
def integration_app():
    """Create app with in-memory database but WITHOUT overriding get_db().

    This ensures we test the real dependency injection path.
    Uses the auth service pattern: patch database objects, don't mess with modules.
    """
    from unittest.mock import MagicMock, patch

    from cl_server_shared.models import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import configure_mappers, sessionmaker
    from sqlalchemy.pool import StaticPool

    from store.store import app
    import store.database as database

    # Create test engine
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Configure versioning
    configure_mappers()

    # Create tables in test database
    Base.metadata.create_all(bind=test_engine)

    # Mock MQTT client
    mock_mqtt_client = MagicMock()
    mock_mqtt_client.get_cached_capabilities.return_value = {}
    mock_mqtt_client.capabilities_cache = {}
    mock_mqtt_client.wait_for_capabilities.return_value = True

    # Patch the module-level engine, SessionLocal, MQTT client, and Config
    from cl_server_shared import Config

    with (
        patch.object(database, "engine", test_engine),
        patch.object(database, "SessionLocal", TestSessionLocal),
        patch.object(Config, "AUTH_DISABLED", True),
    ):
        yield app

    # Cleanup
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def integration_client(integration_app):
    """Test client with NO dependency overrides.

    This is the key to testing the real dependency injection.
    Unlike the standard test client, we don't override get_db().
    """
    with TestClient(integration_app) as client:
        yield client


class TestDependencyInjection:
    """Tests that verify get_db() properly yields a database session."""

    def test_get_db_yields_session_not_generator(self, integration_client):
        """Critical: Verify get_db() yields a Session, not a generator object.

        This test would FAIL with the broken 'return get_db_session()' code
        because FastAPI would inject a generator object instead of a Session.

        With the fixed 'yield from get_db_session()' code, FastAPI properly
        recognizes the generator and injects the yielded Session object.

        If get_db() is broken, this will return 500 with:
        AttributeError: 'generator' object has no attribute 'query'
        """
        # Create a collection entity (doesn't require file upload)
        response = integration_client.post(
            "/entities/", data={"is_collection": "true", "label": "Test Collection"}
        )

        # If get_db() is broken, this will return 500
        assert response.status_code == 201, (
            f"Entity creation failed: {response.json() if response.status_code != 500 else response.text}"
        )
        assert response.json()["label"] == "Test Collection"
        assert response.json()["is_collection"] is True

    def test_root_endpoint_works(self, integration_client):
        """Test root endpoint with real dependency injection."""
        response = integration_client.get("/")
        assert response.status_code == 200
        assert "status" in response.json()
        assert response.json()["status"] == "healthy"

    def test_entity_retrieval_works(self, integration_client):
        """Test entity retrieval with real dependency injection."""
        # Create entity first
        create_response = integration_client.post(
            "/entities/", data={"is_collection": "true", "label": "Test Entity"}
        )
        assert create_response.status_code == 201
        entity_id = create_response.json()["id"]

        # Retrieve entity
        get_response = integration_client.get(f"/entities/{entity_id}")
        assert get_response.status_code == 200
        assert get_response.json()["id"] == entity_id
        assert get_response.json()["label"] == "Test Entity"


class TestEntityOperations:
    """Tests for entity CRUD operations with real dependencies."""

    def test_create_and_update_entity(self, integration_client):
        """Test creating and updating entities through real get_db()."""
        # Create entity
        create_response = integration_client.post(
            "/entities/",
            data={
                "is_collection": "true",
                "label": "Original Name",
                "description": "Original description",
            },
        )
        assert create_response.status_code == 201
        entity_id = create_response.json()["id"]

        # Update entity
        update_response = integration_client.patch(
            f"/entities/{entity_id}",
            json={"body": {"label": "Updated Name", "description": "Updated description"}},
        )
        assert update_response.status_code == 200
        assert update_response.json()["label"] == "Updated Name"
        assert update_response.json()["description"] == "Updated description"

    def test_create_multiple_entities(self, integration_client):
        """Test creating multiple entities to verify session cleanup."""
        entity_ids = []

        for i in range(5):
            response = integration_client.post(
                "/entities/", data={"is_collection": "true", "label": f"Entity {i}"}
            )
            assert response.status_code == 201
            entity_ids.append(response.json()["id"])

        # Verify all entities exist
        for entity_id in entity_ids:
            response = integration_client.get(f"/entities/{entity_id}")
            assert response.status_code == 200

    def test_delete_entity(self, integration_client):
        """Test entity deletion with real dependency injection."""
        # Create entity
        create_response = integration_client.post(
            "/entities/", data={"is_collection": "true", "label": "To Be Deleted"}
        )
        assert create_response.status_code == 201
        entity_id = create_response.json()["id"]

        # Delete entity
        delete_response = integration_client.delete(f"/entities/{entity_id}")
        assert delete_response.status_code == 204

        # Verify entity is deleted (soft delete)
        get_response = integration_client.get(f"/entities/{entity_id}")
        assert get_response.status_code == 404


class TestFileUpload:
    """Tests for file upload operations with real dependencies."""

    def test_file_upload_with_real_dependency(self, integration_client):
        """Test file upload endpoint with real get_db()."""
        # Create a simple test image (1x1 PNG)
        png_data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
            b"\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        # Create entity with file
        create_response = integration_client.post(
            "/entities/",
            data={"is_collection": "false", "label": "Entity with File"},
            files={"image": ("test.png", png_data, "image/png")},
        )
        assert create_response.status_code == 201
        entity_data = create_response.json()
        assert entity_data["file_path"] is not None
        assert entity_data["mime_type"] == "image/png"


class TestMultipleSequentialRequests:
    """Test that database sessions are properly managed across requests."""

    def test_sequential_entity_operations(self, integration_client):
        """Verify sessions are properly created and cleaned up."""
        entity_ids = []

        for i in range(10):
            response = integration_client.post(
                "/entities/", data={"is_collection": "true", "label": f"Seq {i}"}
            )
            assert response.status_code == 201
            entity_ids.append(response.json()["id"])

        # Verify all entities are accessible
        for entity_id in entity_ids:
            response = integration_client.get(f"/entities/{entity_id}")
            assert response.status_code == 200

    def test_mixed_operations_sequential(self, integration_client):
        """Test mixed create/read/update/delete operations."""
        # Create
        create_resp = integration_client.post(
            "/entities/", data={"is_collection": "true", "label": "Mixed Test"}
        )
        assert create_resp.status_code == 201
        entity_id = create_resp.json()["id"]

        # Read
        read_resp = integration_client.get(f"/entities/{entity_id}")
        assert read_resp.status_code == 200

        # Update
        update_resp = integration_client.patch(
            f"/entities/{entity_id}", json={"body": {"label": "Updated Mixed Test"}}
        )
        assert update_resp.status_code == 200

        # Read again
        read_resp2 = integration_client.get(f"/entities/{entity_id}")
        assert read_resp2.status_code == 200
        assert read_resp2.json()["label"] == "Updated Mixed Test"

        # Delete
        delete_resp = integration_client.delete(f"/entities/{entity_id}")
        assert delete_resp.status_code == 204
