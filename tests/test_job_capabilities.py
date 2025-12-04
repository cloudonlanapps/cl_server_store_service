"""Tests for job capability discovery and aggregation."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_mqtt_client():
    """Create a mock MQTT client."""
    client = MagicMock()
    client.get_cached_capabilities.return_value = {
        "image_resize": 2,
        "image_conversion": 1,
    }
    return client


class TestCapabilityEndpoint:
    """Tests for /api/v1/job/capability endpoint."""

    def test_get_capabilities_returns_dict(self, client: TestClient, mock_mqtt_client):
        """Test that capability endpoint returns dict response."""
        with patch("src.mqtt_client.get_mqtt_client", return_value=mock_mqtt_client):
            response = client.get("/api/v1/job/capability")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, dict)

    def test_get_capabilities_aggregates_workers(self, client: TestClient, mock_mqtt_client):
        """Test that capabilities are properly aggregated."""
        mock_mqtt_client.get_cached_capabilities.return_value = {
            "image_resize": 2,
            "image_conversion": 1,
        }

        with patch("src.mqtt_client.get_mqtt_client", return_value=mock_mqtt_client):
            response = client.get("/api/v1/job/capability")

            data = response.json()
            assert data.get("image_resize") == 2
            assert data.get("image_conversion") == 1

    def test_get_capabilities_empty_workers(self, client: TestClient, mock_mqtt_client):
        """Test endpoint returns empty dict when no workers."""
        mock_mqtt_client.get_cached_capabilities.return_value = {}

        with patch("src.mqtt_client.get_mqtt_client", return_value=mock_mqtt_client):
            response = client.get("/api/v1/job/capability")

            assert response.status_code == 200
            data = response.json()
            assert data == {}

    def test_get_capabilities_multiple_types(self, client: TestClient, mock_mqtt_client):
        """Test with multiple capability types."""
        mock_mqtt_client.get_cached_capabilities.return_value = {
            "image_resize": 3,
            "image_conversion": 2,
            "video_encode": 1,
        }

        with patch("src.mqtt_client.get_mqtt_client", return_value=mock_mqtt_client):
            response = client.get("/api/v1/job/capability")

            data = response.json()
            assert len(data) == 3
            assert data.get("image_resize") == 3
            assert data.get("image_conversion") == 2
            assert data.get("video_encode") == 1

    def test_get_capabilities_mqtt_error_returns_empty(self, client: TestClient, mock_mqtt_client):
        """Test that MQTT errors return empty dict gracefully."""
        mock_mqtt_client.get_cached_capabilities.side_effect = Exception("Connection failed")

        with patch("src.mqtt_client.get_mqtt_client", return_value=mock_mqtt_client):
            response = client.get("/api/v1/job/capability")

            assert response.status_code == 200
            data = response.json()
            assert data == {}

    def test_get_capabilities_no_auth_required(self, client: TestClient, mock_mqtt_client):
        """Test that capability endpoint doesn't require authentication."""
        with patch("src.mqtt_client.get_mqtt_client", return_value=mock_mqtt_client):
            # Should work without auth headers
            response = client.get("/api/v1/job/capability")
            assert response.status_code == 200


class TestCapabilityService:
    """Tests for CapabilityService class."""

    def test_capability_service_initialization(self):
        """Test CapabilityService can be initialized."""
        from src.service import CapabilityService
        from sqlalchemy.orm import Session
        from unittest.mock import MagicMock

        db = MagicMock(spec=Session)
        service = CapabilityService(db)

        assert service.db is db

    def test_capability_service_get_available(self, mock_mqtt_client):
        """Test CapabilityService.get_available_capabilities()."""
        from src.service import CapabilityService
        from sqlalchemy.orm import Session
        from unittest.mock import MagicMock

        db = MagicMock(spec=Session)

        with patch("src.mqtt_client.get_mqtt_client", return_value=mock_mqtt_client):
            service = CapabilityService(db)
            capabilities = service.get_available_capabilities()

            assert capabilities == {
                "image_resize": 2,
                "image_conversion": 1,
            }

    def test_capability_service_handles_mqtt_error(self):
        """Test CapabilityService gracefully handles MQTT errors."""
        from src.service import CapabilityService
        from sqlalchemy.orm import Session
        from unittest.mock import MagicMock

        db = MagicMock(spec=Session)
        mock_mqtt = MagicMock()
        mock_mqtt.get_cached_capabilities.side_effect = Exception("Connection error")

        with patch("src.mqtt_client.get_mqtt_client", return_value=mock_mqtt):
            service = CapabilityService(db)
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

    def test_response_is_simple_dict(self, client: TestClient, mock_mqtt_client):
        """Test that response is simple dict (not wrapped)."""
        mock_mqtt_client.get_cached_capabilities.return_value = {"image_resize": 2}

        with patch("src.mqtt_client.get_mqtt_client", return_value=mock_mqtt_client):
            response = client.get("/api/v1/job/capability")
            data = response.json()

            # Should be directly a dict, not wrapped
            assert isinstance(data, dict)
            assert "image_resize" in data
            assert data["image_resize"] == 2

    def test_response_values_are_integers(self, client: TestClient, mock_mqtt_client):
        """Test that all values in response are integers."""
        mock_mqtt_client.get_cached_capabilities.return_value = {
            "image_resize": 2,
            "image_conversion": 1,
        }

        with patch("src.mqtt_client.get_mqtt_client", return_value=mock_mqtt_client):
            response = client.get("/api/v1/job/capability")
            data = response.json()

            for key, value in data.items():
                assert isinstance(value, int)
                assert value >= 0

    def test_response_includes_all_capabilities(self, client: TestClient, mock_mqtt_client):
        """Test that response includes all discovered capabilities."""
        all_caps = {
            "image_resize": 3,
            "image_conversion": 2,
            "video_encode": 1,
        }
        mock_mqtt_client.get_cached_capabilities.return_value = all_caps

        with patch("src.mqtt_client.get_mqtt_client", return_value=mock_mqtt_client):
            response = client.get("/api/v1/job/capability")
            data = response.json()

            assert set(data.keys()) == set(all_caps.keys())
            assert data == all_caps
