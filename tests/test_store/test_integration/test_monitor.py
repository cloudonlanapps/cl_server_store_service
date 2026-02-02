from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from store.store.config import StoreConfig
from store.broadcast_service.monitor import MInsightMonitor


@pytest.fixture
def mock_store_config(integration_config):
    return StoreConfig(
        cl_server_dir=Path("/tmp/fake"),
        media_storage_dir=Path("/tmp/fake/media"),
        public_key_path=Path("/tmp/fake/keys/public_key.pem"),
        no_auth=True,
        port=integration_config.store_port,
        mqtt_url=integration_config.mqtt_url,
    )

def test_monitor_start_disabled(mock_store_config):
    """Test start when MQTT is disabled."""
    mock_store_config.mqtt_url = None
    monitor = MInsightMonitor(mock_store_config)
    monitor.start()
    assert monitor.broadcaster is None

@patch("store.broadcast_service.monitor.get_broadcaster")
def test_monitor_start_enabled(mock_get_broadcaster, mock_store_config):
    """Test successful monitor start."""
    mock_mqtt_broadcaster = MagicMock()
    # Paho client mock
    mock_client = MagicMock()
    mock_mqtt_broadcaster.client = mock_client
    mock_get_broadcaster.return_value = mock_mqtt_broadcaster

    monitor = MInsightMonitor(mock_store_config)
    monitor.start()

    assert monitor.broadcaster == mock_mqtt_broadcaster
    mock_client.subscribe.assert_called()
    mock_client.loop_start.assert_called_once()

@patch("store.broadcast_service.monitor.get_broadcaster")
def test_monitor_start_failure(mock_get_broadcaster, mock_store_config):
    """Test monitor start with exception."""
    mock_get_broadcaster.side_effect = Exception("MQTT Fail")
    monitor = MInsightMonitor(mock_store_config)
    # Should handle exception and not raise
    monitor.start()
    assert monitor.broadcaster is None

def test_monitor_on_message_variants(mock_store_config):
    """Test _on_message with various payloads and topics."""
    monitor = MInsightMonitor(mock_store_config)

    # helper for mock message
    def create_msg(topic, payload):
        msg = MagicMock()
        msg.topic = topic
        msg.payload = payload.encode() if isinstance(payload, str) else payload
        return msg

    # 1. Invalid topic length
    monitor._on_message(None, None, create_msg("short", "{}"))
    assert monitor.process_status is None

    # 2. Invalid port
    monitor._on_message(None, None, create_msg("mInsight/abc/started", "{}"))
    assert monitor.process_status is None

    # 3. Invalid JSON
    monitor._on_message(None, None, create_msg("mInsight/8011/started", "invalid{"))
    assert monitor.process_status is None

    # 4. Valid 'started' message
    monitor._on_message(None, None, create_msg("mInsight/8011/started", '{"version_start":1, "status": "running", "timestamp": 1234567890}'))
    assert monitor.process_status is not None
    assert monitor.process_status.status == "running"
    assert monitor.process_status.version_start == 1

    # 5. Valid 'ended' message
    monitor._on_message(None, None, create_msg("mInsight/8011/ended", '{"processed_count":5, "status": "idle", "timestamp": 1234567895}'))
    assert monitor.process_status.status == "idle"
    assert monitor.process_status.processed_count == 5

    # 6. Valid 'status' message
    monitor._on_message(None, None, create_msg("mInsight/8011/status", '{"status":"custom", "timestamp": 1234567900}'))
    assert monitor.process_status.status == "custom"

def test_monitor_get_status(mock_store_config):
    """Test get_status logic."""
    monitor = MInsightMonitor(mock_store_config)
    from store.broadcast_service.schemas import MInsightStatus
    monitor.process_status = MInsightStatus(status="ok", timestamp=0)

    # Get status
    assert monitor.get_status().status == "ok"

def test_monitor_stop(mock_store_config):
    """Test stop logic."""
    monitor = MInsightMonitor(mock_store_config)
    mock_mqtt = MagicMock()
    mock_client = MagicMock()
    mock_mqtt.client = mock_client
    monitor.broadcaster = mock_mqtt

    monitor.stop()
    mock_client.loop_stop.assert_called_once()
    mock_client.disconnect.assert_called_once()

@patch("cl_ml_tools.get_broadcaster")
def test_monitor_stop_exception(mock_get_broadcaster, mock_store_config):
    """Test stop with exception."""
    monitor = MInsightMonitor(mock_store_config)
    mock_mqtt = MagicMock()
    mock_client = MagicMock()
    mock_client.loop_stop.side_effect = Exception("Fail")
    mock_mqtt.client = mock_client
    monitor.broadcaster = mock_mqtt

    # Should not raise
    monitor.stop()
