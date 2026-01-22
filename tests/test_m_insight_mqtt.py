import json
import time
import pytest
from pathlib import Path
import paho.mqtt.client as mqtt

from store.m_insight.broadcaster import MInsightBroadcaster
from store.m_insight.config import MInsightConfig
from store.m_insight.media_insight import MediaInsight
from store.common import database
from store.common.models import Entity
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def test_subscriber(integration_config):
    """Create an MQTT subscriber for verification."""
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    messages = []
    
    
    def on_message(client, userdata, msg):
        messages.append(msg)
        
    client.on_message = on_message
    port = integration_config.mqtt_port or 1883
    client.connect(integration_config.mqtt_server, port, 60)
    client.loop_start()
    yield client, messages
    client.loop_stop()
    client.disconnect()


@pytest.fixture
def test_m_insight_worker(
    clean_data_dir: Path,
    integration_config,
    test_engine,
):
    """Create mInsight worker with broadcaster for testing."""
    config = MInsightConfig(
        id="test-worker-mqtt",
        cl_server_dir=clean_data_dir,
        media_storage_dir=clean_data_dir / "media",
        public_key_path=clean_data_dir / "keys" / "public_key.pem",
        store_port=integration_config.store_port,
        mqtt_broker=integration_config.mqtt_server,
        mqtt_port=integration_config.mqtt_port,
        mqtt_topic="test/m_insight_mqtt",
    )
    
    # Use test database engine
    database.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    port = integration_config.mqtt_port or 1883
    
    # Update config with valid port
    config.mqtt_port = port
    
    worker = MediaInsight(config=config)
    yield worker


async def test_m_insight_lifecycle_events(
    integration_config,
    test_subscriber,
    test_m_insight_worker,
    test_db_session,
):
    """Test that mInsight worker publishes started/ended events."""
    subscriber, messages = test_subscriber
    worker = test_m_insight_worker
    
    topic_base = f"mInsight/{worker.config.store_port}"
    subscriber.subscribe(f"{topic_base}/#")
    
    # Initialize broadcaster
    broadcaster = MInsightBroadcaster(worker.config)
    broadcaster.init()
    
    # Attach to worker
    worker.broadcaster = broadcaster
    
    # Wait for subscription using paho client state or just sleep
    time.sleep(0.5)
    
    # Create an entity to trigger processing
    entity = Entity(
        is_collection=False,
        label="MQTT Test",
        md5="fake_md5",
        file_path="fake.jpg",
        type="image",
        mime_type="image/jpeg",
        added_date=1,
        updated_date=1,
        create_date=1,
        is_deleted=False
    )
    test_db_session.add(entity)
    test_db_session.commit()
    
    # Run reconciliation
    processed = await worker.run_once()
    assert processed == 1, "Should have processed 1 item"
    
    # Wait for messages
    time.sleep(1.0)
    
    # Verify 'started' message
    started_msgs = [m for m in messages if m.topic.endswith("/started")]
    assert len(started_msgs) >= 1, "Did not receive 'started' message"
    started_payload = json.loads(started_msgs[-1].payload)
    assert "version_start" in started_payload
    assert "version_end" in started_payload
    
    # Verify 'ended' message
    ended_msgs = [m for m in messages if m.topic.endswith("/ended")]
    assert len(ended_msgs) >= 1, "Did not receive 'ended' message"
    ended_payload = json.loads(ended_msgs[-1].payload)
    assert "processed_count" in ended_payload
    assert ended_payload["processed_count"] == processed


def test_m_insight_heartbeat_status(
    integration_config,
    test_subscriber,
    clean_data_dir,
):
    """Test explicit status publishing (heartbeat logic)."""
    subscriber, messages = test_subscriber
    
    # Create config just for broadcaster
    from store.m_insight.config import MInsightConfig
    
    port = integration_config.mqtt_port or 1883
    
    config = MInsightConfig(
        id="test-hb", 
        cl_server_dir=clean_data_dir,
        media_storage_dir=clean_data_dir / "media",
        public_key_path=clean_data_dir / "keys" / "public_key.pem",
        store_port=integration_config.store_port,
        mqtt_broker=integration_config.mqtt_server,
        mqtt_port=port,
    )
    
    topic_base = f"mInsight/{config.store_port}"
    subscriber.subscribe(f"{topic_base}/status")
    time.sleep(0.5)
    
    broadcaster = MInsightBroadcaster(config)
    broadcaster.init()
    
    # Publish 'running'
    broadcaster.publish_status("running")
    time.sleep(0.5)
    
    status_msgs = [m for m in messages if m.topic == f"{topic_base}/status"]
    assert len(status_msgs) >= 1
    payload = json.loads(status_msgs[-1].payload)
    assert payload["status"] == "running"
    
