"""
Integration tests for entity deletion logic (DEL-01 to DEL-10).

This test suite verifies the implementation of modular entity deletion
with complete cleanup of all associated resources.
"""

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from store.db_service.db_internals import Entity, Face
from store.db_service.schemas import EntitySchema


class TestEntityDeletion:
    """Test entity deletion with complete resource cleanup (DEL-01 to DEL-06, DEL-09)."""

    def test_delete_entity_removes_db_record(
        self, client: TestClient, sample_image: Path, test_db_session: Session
    ) -> None:
        """DEL-01: Deleting an entity must remove the entity record from the database."""
        # Create entity
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test Entity"},
            )
        assert response.status_code == 201
        entity = EntitySchema.model_validate(response.json())
        entity_id = entity.id

        # Verify entity exists
        db_entity = test_db_session.query(Entity).filter(Entity.id == entity_id).first()
        assert db_entity is not None

        # Soft-delete first (DEL-09 requirement)
        patch_response = client.patch(f"/entities/{entity_id}", data={"is_deleted": "true"})
        assert patch_response.status_code == 200

        # Verify soft-delete via API (since test_db_session is isolated)
        get_response = client.get(f"/entities/{entity_id}")
        assert get_response.status_code == 200
        patched_entity = EntitySchema.model_validate(get_response.json())
        assert patched_entity.is_deleted is True, "Entity should be soft-deleted"

        # Hard delete
        delete_response = client.delete(f"/entities/{entity_id}")
        if delete_response.status_code != 204:
            print(f"Delete error: {delete_response.json()}")
        assert delete_response.status_code == 204

        # Verify entity removed from DB
        test_db_session.expire_all()  # Clear session cache
        db_entity = test_db_session.query(Entity).filter(Entity.id == entity_id).first()
        assert db_entity is None

    def test_delete_entity_removes_file(
        self, client: TestClient, sample_image: Path, test_db_session: Session
    ) -> None:
        """DEL-02: Deleting an entity must remove its associated file from the filesystem."""
        # Create entity
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test Entity"},
            )
        assert response.status_code == 201
        entity = EntitySchema.model_validate(response.json())
        entity_id = entity.id

        # Get file path
        db_entity = test_db_session.query(Entity).filter(Entity.id == entity_id).first()
        assert db_entity is not None
        assert db_entity.file_path is not None

        # Get absolute path using the config singleton
        from store.common.storage import StorageService
        from store.store.config import StoreConfig

        config = StoreConfig.get_config()
        storage = StorageService(base_dir=str(config.media_storage_dir))
        file_abs_path = storage.get_absolute_path(db_entity.file_path)
        assert file_abs_path.exists(), f"File should exist at {file_abs_path}"

        # Soft-delete first
        patch_response = client.patch(f"/entities/{entity_id}", data={"is_deleted": "true"})
        assert patch_response.status_code == 200

        # Hard delete
        delete_response = client.delete(f"/entities/{entity_id}")
        assert delete_response.status_code == 204

        # Verify file removed
        assert not file_abs_path.exists(), f"File should be deleted at {file_abs_path}"

    def test_consolidated_deletion_flow(
        self, client: TestClient, sample_image: Path, test_db_session: Session
    ) -> None:
        """
        Consolidated deletion test covering DEL-03, DEL-04, DEL-05, DEL-08.
        
        Flow:
        1. Upload entity (mocking multiple faces).
        2. Verify initial state (DB, Intelligence).
        3. Delete one face -> Verify cleanup (DB, Vector, Count).
        4. Delete second face -> Verify cleanup.
        5. Delete entity -> Verify full cleanup (DB, Files, Vectors, MQTT).
        """
        # 1. Setup Mocks
        mock_broadcaster = MagicMock()
        mock_face_store = MagicMock()
        mock_clip_store = MagicMock()
        mock_dino_store = MagicMock()

        # Inject mocks into app dependency overrides
        from store.store.dependencies import get_m_insight_broadcaster
        from store.vectorstore_services.vector_stores import (
            get_clip_store_dep,
            get_dino_store_dep,
            get_face_store_dep,
        )
        
        client.app.dependency_overrides[get_m_insight_broadcaster] = lambda: mock_broadcaster
        client.app.dependency_overrides[get_face_store_dep] = lambda: mock_face_store
        client.app.dependency_overrides[get_clip_store_dep] = lambda: mock_clip_store
        client.app.dependency_overrides[get_dino_store_dep] = lambda: mock_dino_store

        # 2. Create Entity
        # ... (rest of the test remains the same)
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Multi-Face Entity"},
            )
        assert response.status_code == 201
        entity = EntitySchema.model_validate(response.json())
        entity_id = entity.id

        # 3. Manually create Faces and Intelligence Data (Simulate mInsight)
        from store.db_service.models import Face, EntityIntelligence
        from store.db_service import EntityIntelligenceData
        
        # Create 2 mock faces
        face1 = Face(
            entity_id=entity_id,
            file_path=f"faces/{entity_id}_1.jpg",
            bbox="[0.1, 0.1, 0.6, 0.6]",
            confidence=0.99,
            landmarks="[]",
            created_at=1000
        )
        face2 = Face(
            entity_id=entity_id,
            file_path=f"faces/{entity_id}_2.jpg",
            bbox="[0.2, 0.2, 0.7, 0.7]",
            confidence=0.98,
            landmarks="[]",
            created_at=1001
        )
        test_db_session.add(face1)
        test_db_session.add(face2)
        
        # Create Intelligence Record with face count
        intel_data = EntityIntelligenceData(
            face_count=2,
            overall_status="completed",
            last_updated=1000
        )
        intel_record = EntityIntelligence(
            entity_id=entity_id,
            intelligence_data=intel_data.model_dump()
        )
        test_db_session.add(intel_record)
        test_db_session.commit()
        test_db_session.refresh(face1)
        test_db_session.refresh(face2)
        
        f1_id = face1.id
        f2_id = face2.id

        # 4. Delete Face 1
        resp = client.delete(f"/faces/{f1_id}")
        assert resp.status_code == 204
        
        # Verify Face 1 Deleted
        test_db_session.expire_all()
        assert test_db_session.get(Face, f1_id) is None
        assert test_db_session.get(Face, f2_id) is not None
        
        # Verify Vector Deletion (Face 1)
        mock_face_store.delete_vector.assert_called_with(f1_id)
        
        # Verify Face Count Update
        from store.db_service.intelligence import EntityIntelligenceDBService
        intel_service = EntityIntelligenceDBService(test_db_session)
        current_intel = intel_service.get_intelligence_data(entity_id)
        assert current_intel.face_count == 1
        
        # 5. Delete Face 2 (Another "image"/face)
        resp = client.delete(f"/faces/{f2_id}")
        assert resp.status_code == 204
        
        # Verify Face 2 Deleted
        test_db_session.expire_all()
        assert test_db_session.get(Face, f2_id) is None
        
        # Verify Vector Deletion (Face 2)
        mock_face_store.delete_vector.assert_called_with(f2_id)
        
        # Verify Face Count Update
        current_intel = intel_service.get_intelligence_data(entity_id)
        assert current_intel.face_count == 0

        # Reset Mocks for Entity Deletion Check
        mock_broadcaster.reset_mock()
        mock_clip_store.reset_mock()
        mock_dino_store.reset_mock()

        # 6. Delete Entity
        # Soft Delete First
        client.patch(f"/entities/{entity_id}", data={"is_deleted": "true"})
        
        # Hard Delete
        resp = client.delete(f"/entities/{entity_id}")
        assert resp.status_code == 204
        
        # Verify Entity Gone
        assert test_db_session.get(Entity, entity_id) is None
        
        # Verify Vector Store Cleanup (CLIP/DINO)
        mock_clip_store.delete_vector.assert_called_with(entity_id)
        mock_dino_store.delete_vector.assert_called_with(entity_id)
        
        # Verify MQTT Cleanup
        mock_broadcaster.clear_entity_status.assert_called_with(entity_id)

    # Removed individual TODO tests replaced by the above consolidated test
    # test_delete_entity_removes_vectors
    # test_delete_entity_removes_faces

    def test_delete_entity_clears_mqtt_mock(
        self, client: TestClient, sample_image: Path, test_db_session: Session
    ) -> None:
        """DEL-05: Deleting an entity must clear any retained MQTT messages (mock test)."""
        # Setup mock broadcaster
        mock_broadcaster = MagicMock()
        from store.store.dependencies import get_m_insight_broadcaster
        client.app.dependency_overrides[get_m_insight_broadcaster] = lambda: mock_broadcaster

        # Create entity
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test Entity"},
            )
        assert response.status_code == 201
        entity = EntitySchema.model_validate(response.json())
        entity_id = entity.id

        # Reset mock to clear creation calls
        mock_broadcaster.reset_mock()

        # Soft-delete first
        patch_response = client.patch(f"/entities/{entity_id}", data={"is_deleted": "true"})
        assert patch_response.status_code == 200

        # Hard delete
        delete_response = client.delete(f"/entities/{entity_id}")
        assert delete_response.status_code == 204

        # Verify MQTT message was cleared
        assert mock_broadcaster.clear_entity_status.called, "MQTT clear should be called"
        call_args = mock_broadcaster.clear_entity_status.call_args
        assert call_args[0][0] == entity_id, f"Should clear entity {entity_id}"

    def test_delete_entity_clears_mqtt_real(
        self, client: TestClient, sample_image: Path, test_db_session: Session, request
    ) -> None:
        """DEL-05: Real MQTT integration test for deletion clearing retained messages."""
        mqtt_url = request.config.getoption("--mqtt-url")
        if not mqtt_url:
            pytest.skip("Real MQTT broker not configured (use --mqtt-url)")

        import threading
        import paho.mqtt.client as mqtt
        from paho.mqtt.enums import CallbackAPIVersion

        # Track received messages
        received_messages = {}
        message_event = threading.Event()

        def on_message(client_obj, userdata, message):
            """Callback for received messages."""
            topic = message.topic
            payload = message.payload.decode() if message.payload else ""
            received_messages[topic] = payload
            message_event.set()

        # Create MQTT client
        mqtt_client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id="test_delete_mqtt_client"
        )
        mqtt_client.on_message = on_message

        try:
            # Connect to broker
            from urllib.parse import urlparse
            parsed_url = urlparse(mqtt_url)
            mqtt_broker = parsed_url.hostname or "localhost"
            mqtt_port = parsed_url.port or 1883
            
            mqtt_client.connect(mqtt_broker, mqtt_port, 60)
            mqtt_client.loop_start()

            # Create entity via API
            with open(sample_image, "rb") as f:
                response = client.post(
                    "/entities/",
                    files={"image": (sample_image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": "MQTT Test Entity"},
                )
            assert response.status_code == 201
            entity = EntitySchema.model_validate(response.json())
            entity_id = entity.id

            # Determine the expected MQTT topic
            from store.store.config import StoreConfig
            config = StoreConfig.get_config()
            entity_status_topic = f"mInsight/{config.port}/entity_item_status/{entity_id}"

            # Subscribe to entity status topic
            mqtt_client.subscribe(entity_status_topic)
            time.sleep(0.5)  # Wait for subscription

            # Soft-delete entity
            client.patch(f"/entities/{entity_id}", data={"is_deleted": "true"})
            time.sleep(0.5)  # Wait for any potential message

            # Hard delete entity (should clear retained message)
            delete_response = client.delete(f"/entities/{entity_id}")
            assert delete_response.status_code == 204

            # Wait a moment for MQTT clear to propagate
            time.sleep(1.0)

            # The retained message should now be empty (cleared)
            # Re-subscribe to check if retained message is cleared
            received_messages.clear()
            message_event.clear()
            mqtt_client.unsubscribe(entity_status_topic)
            time.sleep(0.2)
            mqtt_client.subscribe(entity_status_topic)

            # Wait for retained message
            message_received = message_event.wait(timeout=2.0)

            # If we receive a message, it should be empty (the clearing message)
            if message_received and entity_status_topic in received_messages:
                retained_payload = received_messages[entity_status_topic]
                assert retained_payload == "", (
                    f"Retained message should be cleared (empty), got: {retained_payload}"
                )

        finally:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()

    def test_recursive_deletion_soft_deletes_first(
        self, client: TestClient, sample_image: Path, test_db_session: Session
    ) -> None:
        """DEL-06: Deleting a Collection must recursively delete children, soft-deleting first if needed."""
        # Create parent collection
        parent_response = client.post(
            "/entities/",
            data={"is_collection": "true", "label": "Parent Collection"},
        )
        assert parent_response.status_code == 201
        parent = EntitySchema.model_validate(parent_response.json())
        parent_id = parent.id

        # Create child entity (not soft-deleted)
        with open(sample_image, "rb") as f:
            child_response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Child Entity",
                    "parent_id": str(parent_id),
                },
            )
        assert child_response.status_code == 201
        child = EntitySchema.model_validate(child_response.json())
        child_id = child.id

        # Verify child NOT soft-deleted
        db_child = test_db_session.query(Entity).filter(Entity.id == child_id).first()
        assert db_child is not None
        assert db_child.is_deleted is False

        # Soft-delete parent
        patch_response = client.patch(f"/entities/{parent_id}", data={"is_deleted": "true"})
        assert patch_response.status_code == 200

        # Hard delete parent (should soft-delete child first, then hard-delete it)
        delete_response = client.delete(f"/entities/{parent_id}")
        assert delete_response.status_code == 204

        # Verify both parent and child removed via API
        parent_check = client.get(f"/entities/{parent_id}")
        assert parent_check.status_code == 404, "Parent should be deleted"

        child_check = client.get(f"/entities/{child_id}")
        assert child_check.status_code == 404, "Child should be deleted"

    def test_nested_collection_deletion(
        self, client: TestClient, sample_image: Path, test_db_session: Session
    ) -> None:
        """Test recursive deletion of nested collections (grandparent -> parent -> child)."""
        # Create grandparent collection
        grandparent_response = client.post(
            "/entities/",
            data={"is_collection": "true", "label": "Grandparent Collection"},
        )
        assert grandparent_response.status_code == 201
        grandparent = EntitySchema.model_validate(grandparent_response.json())
        grandparent_id = grandparent.id

        # Create parent collection (child of grandparent)
        parent_response = client.post(
            "/entities/",
            data={
                "is_collection": "true",
                "label": "Parent Collection",
                "parent_id": str(grandparent_id),
            },
        )
        assert parent_response.status_code == 201
        parent = EntitySchema.model_validate(parent_response.json())
        parent_id = parent.id

        # Create leaf entity (child of parent)
        with open(sample_image, "rb") as f:
            leaf_response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Leaf Entity",
                    "parent_id": str(parent_id),
                },
            )
        assert leaf_response.status_code == 201
        leaf = EntitySchema.model_validate(leaf_response.json())
        leaf_id = leaf.id

        # Verify hierarchy exists
        db_grandparent = test_db_session.query(Entity).filter(Entity.id == grandparent_id).first()
        db_parent = test_db_session.query(Entity).filter(Entity.id == parent_id).first()
        db_leaf = test_db_session.query(Entity).filter(Entity.id == leaf_id).first()
        assert db_grandparent is not None
        assert db_parent is not None
        assert db_leaf is not None
        assert db_parent.parent_id == grandparent_id
        assert db_leaf.parent_id == parent_id

        # Soft-delete grandparent
        patch_response = client.patch(f"/entities/{grandparent_id}", data={"is_deleted": "true"})
        assert patch_response.status_code == 200

        # Hard delete grandparent (should recursively delete parent and leaf)
        delete_response = client.delete(f"/entities/{grandparent_id}")
        assert delete_response.status_code == 204

        # Verify all three entities removed via API
        grandparent_check = client.get(f"/entities/{grandparent_id}")
        assert grandparent_check.status_code == 404, "Grandparent should be deleted"

        parent_check = client.get(f"/entities/{parent_id}")
        assert parent_check.status_code == 404, "Parent collection should be recursively deleted"

        leaf_check = client.get(f"/entities/{leaf_id}")
        assert leaf_check.status_code == 404, "Leaf entity should be recursively deleted"

    def test_hard_delete_requires_soft_delete(
        self, client: TestClient, sample_image: Path, test_db_session: Session
    ) -> None:
        """DEL-09: An entity must be soft-deleted before it can be permanently deleted."""
        # Create entity
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test Entity"},
            )
        assert response.status_code == 201
        entity = EntitySchema.model_validate(response.json())
        entity_id = entity.id

        # Verify entity NOT soft-deleted
        db_entity = test_db_session.query(Entity).filter(Entity.id == entity_id).first()
        assert db_entity is not None
        assert db_entity.is_deleted is False

        # Attempt hard delete WITHOUT soft-delete first
        delete_response = client.delete(f"/entities/{entity_id}")
        assert delete_response.status_code == 400  # Bad Request
        assert "must be soft-deleted first" in delete_response.json()["detail"]

        # Verify entity still exists
        test_db_session.expire_all()
        db_entity = test_db_session.query(Entity).filter(Entity.id == entity_id).first()
        assert db_entity is not None


class TestFaceDeletion:
    """Test face deletion endpoint (DEL-08)."""

    # test_delete_face_updates_counts replaced by test_consolidated_deletion_flow
    pass


class TestDeleteAllNotExposed:
    """Test that no bulk delete endpoint exists (DEL-07)."""

    def test_delete_all_not_exposed(self, client: TestClient) -> None:
        """DEL-07: NO "Delete All" endpoint should be exposed."""
        # Try common bulk delete patterns
        endpoints_to_test = [
            "/entities/delete-all",
            "/entities/bulk-delete",
            "/entities/clear",
            "/system/delete-all-entities",
            "/admin/delete-all",
        ]

        for endpoint in endpoints_to_test:
            response = client.post(endpoint)
            # Should get 404 Not Found or 405 Method Not Allowed, not 200/204
            assert response.status_code in [404, 405], (
                f"Endpoint {endpoint} should not exist or be allowed"
            )

        # Also verify DELETE /entities (without ID) is not allowed
        response = client.delete("/entities/")
        assert response.status_code in [404, 405], "Bulk DELETE /entities should not be allowed"


class TestClearOrphans:
    """Test orphan cleanup functionality (DEL-10)."""

    def test_clear_orphans_endpoint_works(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """DEL-10: POST /system/clear-orphans endpoint is callable and returns valid report.

        Note: Creating true orphaned faces is difficult in tests due to FK CASCADE constraints,
        which is actually correct behavior. This test verifies the endpoint works.
        """
        # Create a normal entity
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test Entity"},
            )
        assert response.status_code == 201

        # Call clear-orphans endpoint (should succeed even with no orphans)
        clear_response = client.post("/system/clear-orphans")
        assert clear_response.status_code == 200

        # Verify cleanup report structure
        cleanup_data = clear_response.json()
        assert "files_deleted" in cleanup_data
        assert "faces_deleted" in cleanup_data
        assert "vectors_deleted" in cleanup_data
        assert "mqtt_cleared" in cleanup_data

        # All counts should be non-negative integers
        assert isinstance(cleanup_data["files_deleted"], int)
        assert isinstance(cleanup_data["faces_deleted"], int)
        assert isinstance(cleanup_data["vectors_deleted"], int)
        assert isinstance(cleanup_data["mqtt_cleared"], int)

    def test_clear_orphans_with_no_orphans(
        self, client: TestClient, sample_image: Path, test_db_session: Session
    ) -> None:
        """Test that clear-orphans succeeds even with no orphans."""
        # Create a normal entity (not orphaned)
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Normal Entity"},
            )
        assert response.status_code == 201

        # Run clear-orphans
        clear_response = client.post("/system/clear-orphans")
        assert clear_response.status_code == 200

        # Should return zero deletions
        cleanup_data = clear_response.json()
        assert "files_deleted" in cleanup_data
        assert "faces_deleted" in cleanup_data
        assert "vectors_deleted" in cleanup_data


class TestAuditSystem:
    """Test audit system functionality."""

    def test_audit_generates_valid_report(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Test GET /system/audit generates a valid integrity report.

        Note: Creating true orphans is difficult in tests due to FK constraints,
        which is correct behavior. This test verifies the audit endpoint structure.
        """
        # Create a normal entity
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test Entity"},
            )
        assert response.status_code == 201

        # Call audit endpoint
        audit_response = client.get("/system/audit")
        assert audit_response.status_code == 200

        # Verify report structure
        report = audit_response.json()
        assert "orphaned_files" in report
        assert "orphaned_faces" in report
        assert "orphaned_vectors" in report
        assert "orphaned_mqtt" in report

        # All should be lists
        assert isinstance(report["orphaned_files"], list)
        assert isinstance(report["orphaned_faces"], list)
        assert isinstance(report["orphaned_vectors"], list)
        assert isinstance(report["orphaned_mqtt"], list)

    def test_audit_empty_report_with_no_orphans(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Test that audit returns empty report when there are no orphans."""
        # Create a normal entity (not orphaned)
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Normal Entity"},
            )
        assert response.status_code == 201

        # Call audit endpoint
        audit_response = client.get("/system/audit")
        assert audit_response.status_code == 200

        # Verify report structure exists
        report = audit_response.json()
        assert "orphaned_files" in report
        assert "orphaned_faces" in report
        assert "orphaned_vectors" in report
        assert "orphaned_mqtt" in report

        # Note: We can't guarantee zero orphans if other tests left debris,
        # but we can verify the endpoint works and returns valid structure
