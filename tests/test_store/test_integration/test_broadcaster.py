from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from store.broadcast_service.broadcaster import MInsightBroadcaster
from store.m_insight.config import MInsightConfig


@pytest.fixture
def mock_config(integration_config):
    return MInsightConfig(
        id="test-broadcaster",
        cl_server_dir=Path("/tmp/fake"),
        media_storage_dir=Path("/tmp/fake/media"),
        public_key_path=Path("/tmp/fake/keys/public_key.pem"),
        mqtt_url="mqtt://mock-broker:1883"
    )



@patch("store.broadcast_service.broadcaster.get_broadcaster")
def test_broadcaster_init_enabled(mock_get_broadcaster, mock_config):
    """Test successful initialization with MQTT."""
    mock_mqtt_broadcaster = MagicMock()
    mock_get_broadcaster.return_value = mock_mqtt_broadcaster

    broadcaster = MInsightBroadcaster(mock_config)
    broadcaster.init()

    assert broadcaster.broadcaster == mock_mqtt_broadcaster
    mock_get_broadcaster.assert_called_once_with(
        url="mqtt://mock-broker:1883"
    )
    mock_mqtt_broadcaster.set_will.assert_called_once()

def test_broadcaster_publish_no_init(mock_config):
    """Test methods when broadcaster is not initialized."""
    broadcaster = MInsightBroadcaster(mock_config)
    # Should not raise
    broadcaster.publish_start(1, 2)
    broadcaster.publish_end(5)
    broadcaster.publish_status("running")

@patch("store.broadcast_service.broadcaster.get_broadcaster")
def test_broadcaster_publish_methods(mock_get_broadcaster, mock_config):
    """Test various publish methods."""
    mock_mqtt_broadcaster = MagicMock()
    mock_get_broadcaster.return_value = mock_mqtt_broadcaster

    broadcaster = MInsightBroadcaster(mock_config)
    broadcaster.init()

    broadcaster.publish_start(100, 105)
    mock_mqtt_broadcaster.publish_retained.assert_called()

    broadcaster.publish_end(10)
    mock_mqtt_broadcaster.publish_retained.assert_called()

    broadcaster.publish_status("online")
    mock_mqtt_broadcaster.publish_retained.assert_called()
