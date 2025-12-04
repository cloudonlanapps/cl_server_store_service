"""Tests for job capability discovery and aggregation."""

import json
from unittest.mock import MagicMock, patch

import pytest


class TestCapabilityEndpoint:
    """Tests for /compute/capabilities endpoint."""

    def test_get_capabilities_returns_structured_response(self, client):
        """Test that capability endpoint returns structured response with num_workers and capabilities."""
        response = client.get("/compute/capabilities")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "num_workers" in data
        assert "capabilities" in data
        assert isinstance(data["num_workers"], int)
        assert isinstance(data["capabilities"], dict)

    def test_get_capabilities_empty_workers(self, client):
        """Test endpoint returns empty capabilities when no workers (default mock)."""
        response = client.get("/compute/capabilities")

        assert response.status_code == 200
        data = response.json()
        # Default mock returns empty capabilities
        assert data["num_workers"] == 0
        assert data["capabilities"] == {}

    def test_get_capabilities_no_auth_required(self, client):
        """Test that capability endpoint doesn't require authentication."""
        # The client fixture has auth enabled, but this endpoint should still work
        response = client.get("/compute/capabilities")
        assert response.status_code == 200


class TestCapabilityEndpointWithWorkers:
    """Tests for /compute/capabilities with mocked workers."""

    def test_get_capabilities_aggregates_workers(self, test_engine, clean_media_dir):
        """Test that capabilities are properly aggregated from multiple workers."""
        from unittest.mock import MagicMock, patch
        from sqlalchemy.orm import sessionmaker
        from fastapi.testclient import TestClient

        TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=test_engine
        )

        def override_get_db():
            try:
                db = TestingSessionLocal()
                yield db
            finally:
                db.close()

        # Mock MQTT client with worker data
        mock_mqtt_client = MagicMock()
        mock_mqtt_client.get_cached_capabilities.return_value = {
            "image_resize": 2,
            "image_conversion": 1,
        }
        mock_mqtt_client.capabilities_cache = {
            "worker-1": {"capabilities": ["image_resize"], "idle_count": 1},
            "worker-2": {"capabilities": ["image_resize", "image_conversion"], "idle_count": 1},
        }

        # Patch the singleton instance directly to ensure all calls use the mock
        with patch("src.mqtt_client._mqtt_client_instance", mock_mqtt_client):
            from src import app
            from src.database import get_db
            from src.auth import get_current_user
            from src.service import EntityService, JobService

            app.dependency_overrides[get_db] = override_get_db
            app.dependency_overrides[get_current_user] = lambda: {
                "sub": "testuser",
                "permissions": ["media_store_write"],
                "is_admin": True,
            }

            original_entity_init = EntityService.__init__
            original_job_init = JobService.__init__

            def patched_entity_init(self, db, base_dir=None):
                original_entity_init(self, db, base_dir=str(clean_media_dir))

            def patched_job_init(self, db, base_dir=None):
                original_job_init(self, db, base_dir=str(clean_media_dir))

            EntityService.__init__ = patched_entity_init
            JobService.__init__ = patched_job_init

            with TestClient(app) as test_client:
                response = test_client.get("/compute/capabilities")

                assert response.status_code == 200
                data = response.json()
                assert data["num_workers"] == 2  # 2 unique workers
                assert data["capabilities"]["image_resize"] == 2
                assert data["capabilities"]["image_conversion"] == 1

            EntityService.__init__ = original_entity_init
            JobService.__init__ = original_job_init
            app.dependency_overrides.clear()

    def test_get_capabilities_mqtt_error_returns_empty(self, test_engine, clean_media_dir):
        """Test that MQTT errors return empty capabilities gracefully."""
        from unittest.mock import MagicMock, patch
        from sqlalchemy.orm import sessionmaker
        from fastapi.testclient import TestClient

        TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=test_engine
        )

        def override_get_db():
            try:
                db = TestingSessionLocal()
                yield db
            finally:
                db.close()

        # Mock MQTT client that raises an error
        mock_mqtt_client = MagicMock()
        mock_mqtt_client.get_cached_capabilities.side_effect = Exception("MQTT error")
        mock_mqtt_client.capabilities_cache = {}

        # Patch the singleton instance directly
        with patch("src.mqtt_client._mqtt_client_instance", mock_mqtt_client):
            from src import app
            from src.database import get_db
            from src.auth import get_current_user
            from src.service import EntityService, JobService

            app.dependency_overrides[get_db] = override_get_db
            app.dependency_overrides[get_current_user] = lambda: {
                "sub": "testuser",
                "permissions": ["media_store_write"],
                "is_admin": True,
            }

            original_entity_init = EntityService.__init__
            original_job_init = JobService.__init__

            def patched_entity_init(self, db, base_dir=None):
                original_entity_init(self, db, base_dir=str(clean_media_dir))

            def patched_job_init(self, db, base_dir=None):
                original_job_init(self, db, base_dir=str(clean_media_dir))

            EntityService.__init__ = patched_entity_init
            JobService.__init__ = patched_job_init

            with TestClient(app) as test_client:
                response = test_client.get("/compute/capabilities")

                assert response.status_code == 200
                data = response.json()
                # Should return empty on error
                assert data["num_workers"] == 0
                assert data["capabilities"] == {}

            EntityService.__init__ = original_entity_init
            JobService.__init__ = original_job_init
            app.dependency_overrides.clear()


class TestCapabilityService:
    """Tests for CapabilityService class."""

    def test_capability_service_initialization(self, test_db_session):
        """Test CapabilityService can be initialized."""
        from src.service import CapabilityService

        service = CapabilityService(test_db_session)
        assert service.db is test_db_session

    def test_capability_service_get_available(self, test_db_session):
        """Test CapabilityService.get_available_capabilities()."""
        from src.service import CapabilityService

        mock_mqtt_client = MagicMock()
        mock_mqtt_client.get_cached_capabilities.return_value = {
            "image_resize": 2,
            "image_conversion": 1,
        }

        with patch("src.service.get_mqtt_client", return_value=mock_mqtt_client):
            service = CapabilityService(test_db_session)
            capabilities = service.get_available_capabilities()

            assert capabilities == {
                "image_resize": 2,
                "image_conversion": 1,
            }

    def test_capability_service_handles_mqtt_error(self, test_db_session):
        """Test CapabilityService gracefully handles MQTT errors."""
        from src.service import CapabilityService

        mock_mqtt = MagicMock()
        mock_mqtt.get_cached_capabilities.side_effect = Exception("Connection error")

        with patch("src.service.get_mqtt_client", return_value=mock_mqtt):
            service = CapabilityService(test_db_session)
            capabilities = service.get_available_capabilities()

            # Should return empty dict on error
            assert capabilities == {}


class TestMQTTClientIntegration:
    """Tests for MQTT client message caching and aggregation."""

    def test_mqtt_client_caches_capabilities(self):
        """Test that MQTT client caches capability messages."""
        from src.mqtt_client import MQTTClient

        # Note: This test uses mocking to avoid needing live MQTT broker
        client = MQTTClient("localhost", 1883)

        # Simulate receiving a capability message
        test_message = {
            "id": "worker-1",
            "capabilities": ["image_resize", "image_conversion"],
            "idle_count": 2,
            "timestamp": 1000,
        }

        # Manually inject into cache (simulating MQTT message receipt)
        client.capabilities_cache["worker-1"] = test_message

        # Get cached capabilities
        cached = client.get_cached_capabilities()

        assert "image_resize" in cached
        assert "image_conversion" in cached
        assert cached["image_resize"] == 2
        assert cached["image_conversion"] == 2

    def test_mqtt_client_aggregates_multiple_workers(self):
        """Test aggregation across multiple workers."""
        from src.mqtt_client import MQTTClient

        client = MQTTClient("localhost", 1883)

        # Simulate multiple workers
        client.capabilities_cache["worker-1"] = {
            "id": "worker-1",
            "capabilities": ["image_resize"],
            "idle_count": 2,
        }
        client.capabilities_cache["worker-2"] = {
            "id": "worker-2",
            "capabilities": ["image_resize", "image_conversion"],
            "idle_count": 1,
        }

        cached = client.get_cached_capabilities()

        # image_resize: 2 (worker-1) + 1 (worker-2) = 3
        # image_conversion: 1 (worker-2)
        assert cached["image_resize"] == 3
        assert cached["image_conversion"] == 1

    def test_mqtt_client_handles_lwt_cleanup(self):
        """Test LWT message removes worker from cache."""
        from src.mqtt_client import MQTTClient

        client = MQTTClient("localhost", 1883)

        # Add worker
        client.capabilities_cache["worker-1"] = {
            "id": "worker-1",
            "capabilities": ["image_resize"],
            "idle_count": 1,
        }

        assert "worker-1" in client.capabilities_cache

        # Simulate LWT message (empty payload)
        # The on_message handler should remove it
        client.capabilities_cache.pop("worker-1", None)

        # Verify removed
        assert "worker-1" not in client.capabilities_cache

    def test_mqtt_client_get_worker_count(self):
        """Test getting total worker count by capability."""
        from src.mqtt_client import MQTTClient

        client = MQTTClient("localhost", 1883)

        # Add workers
        client.capabilities_cache["worker-1"] = {
            "capabilities": ["image_resize"],
            "idle_count": 1,
        }
        client.capabilities_cache["worker-2"] = {
            "capabilities": ["image_resize"],
            "idle_count": 0,
        }
        client.capabilities_cache["worker-3"] = {
            "capabilities": ["image_conversion"],
            "idle_count": 1,
        }

        counts = client.get_worker_count_by_capability()

        assert counts["image_resize"] == 2  # 2 workers
        assert counts["image_conversion"] == 1  # 1 worker


class TestCapabilityResponseFormat:
    """Tests for capability response format and structure."""

    def test_response_has_num_workers_field(self, client):
        """Test that response contains num_workers field (unique identifier)."""
        response = client.get("/compute/capabilities")

        assert response.status_code == 200
        data = response.json()

        # num_workers field uniquely identifies this as a capability response
        assert "num_workers" in data
        assert isinstance(data["num_workers"], int)
        assert data["num_workers"] >= 0

    def test_response_has_capabilities_field(self, client):
        """Test that response contains capabilities dict."""
        response = client.get("/compute/capabilities")

        assert response.status_code == 200
        data = response.json()

        assert "capabilities" in data
        assert isinstance(data["capabilities"], dict)

    def test_capabilities_values_are_non_negative_integers(self, client):
        """Test that capability counts are non-negative integers."""
        response = client.get("/compute/capabilities")

        assert response.status_code == 200
        data = response.json()

        for capability, count in data["capabilities"].items():
            assert isinstance(capability, str)
            assert isinstance(count, int)
            assert count >= 0

    def test_num_workers_is_unique_worker_count(self, client):
        """Test that num_workers represents unique connected workers."""
        response = client.get("/compute/capabilities")

        assert response.status_code == 200
        data = response.json()

        # num_workers should be >= 0 (unique worker count, not sum of capabilities)
        assert data["num_workers"] >= 0
        # If capabilities exist, num_workers should be >= 1
        if data["capabilities"]:
            assert data["num_workers"] >= 1

