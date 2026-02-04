import json
import random
import time
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest
from sqlalchemy.orm import sessionmaker

from store.db_service.db_internals import database
from store.db_service.db_internals import Entity
from store.broadcast_service.schemas import MInsightStatus
from store.broadcast_service.broadcaster import MInsightBroadcaster
from store.m_insight.config import MInsightConfig
from store.m_insight.media_insight import MediaInsight


@pytest.fixture
def test_subscriber(integration_config):
    """Create an MQTT subscriber for verification."""
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    messages = []


    def on_message(client, userdata, msg):
        messages.append(msg)

    client.on_message = on_message
    # Parse URL
    from requests.compat import urlparse
    parsed = urlparse(integration_config.mqtt_url)
    broker = parsed.hostname or "localhost"
    port = parsed.port or 1883
    
    client.connect(broker, port, 60)
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
        store_port=random.randint(30000, 40000),
        mqtt_url=integration_config.mqtt_url,
        mqtt_topic="test/m_insight_mqtt",
    )

    # Use test database engine
    database.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Valid URL is already in config
    pass

    # Initialize broadcaster
    broadcaster = MInsightBroadcaster(config)
    broadcaster.init()

    # Create worker with broadcaster
    worker = MediaInsight(config=config, broadcaster=broadcaster)
    yield worker


@pytest.mark.asyncio
async def test_m_insight_lifecycle_events(
    integration_config,
    test_subscriber,
    test_m_insight_worker,
    test_db_session,
):
    """Test that mInsight worker publishes unified status events during lifecycle."""
    subscriber, messages = test_subscriber
    worker = test_m_insight_worker

    topic_base = f"mInsight/{worker.config.store_port}"
    # All events now go to /status topic
    subscriber.subscribe(f"{topic_base}/status")

    # Wait for subscription and clear any retained messages
    time.sleep(1.0)
    messages.clear()

    # Create dummy file
    media_dir = worker.config.media_storage_dir
    media_dir.mkdir(parents=True, exist_ok=True)
    (media_dir / "fake.jpg").write_bytes(b"fake image data")

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

    # Wait for messages with timeout
    start_time = time.time()
    while time.time() - start_time < 5.0:
        status_msg_payloads = [
            MInsightStatus.model_validate_json(m.payload)
            for m in messages
            if m.topic == f"{topic_base}/status"
        ]
        if len(status_msg_payloads) >= 2:
            break
        time.sleep(0.1)
    
    assert len(status_msg_payloads) >= 2, f"Expected at least 2 status messages, got {len(status_msg_payloads)}"

    # Sort by timestamp to ensure correct order
    status_msg_payloads.sort(key=lambda s: s.timestamp)
    
    # Last messages should contain 'idle' and 'running'
    statuses = [s.status for s in status_msg_payloads]
    assert "idle" in statuses
    assert "running" in statuses
    assert status_msg_payloads[-1].processed_count == processed

    # One of the messages should be 'running' (published at start of run_once)
    running_msgs = [s for s in status_msg_payloads if s.status == "running"]
    assert len(running_msgs) >= 1, "Did not receive 'running' status message"
    # The one from publish_start should have version info set
    running_with_info = [s for s in running_msgs if s.version_start is not None]
    assert len(running_with_info) >= 1, "Did not receive 'running' status with version info"
    assert running_with_info[0].version_start is not None
    assert running_with_info[0].version_end is not None


def test_m_insight_heartbeat_status(
    integration_config,
    test_subscriber,
    clean_data_dir,
):
    """Test explicit status publishing (heartbeat logic)."""
    subscriber, messages = test_subscriber



    config = MInsightConfig(
        id="test-hb",
        cl_server_dir=clean_data_dir,
        media_storage_dir=clean_data_dir / "media",
        public_key_path=clean_data_dir / "keys" / "public_key.pem",
        store_port=random.randint(40001, 50000),
        mqtt_url=integration_config.mqtt_url,
    )

    topic_base = f"mInsight/{config.store_port}"
    subscriber.subscribe(f"{topic_base}/status")
    time.sleep(0.5)
    messages.clear()

    broadcaster = MInsightBroadcaster(config)
    broadcaster.init()

    # Publish 'running'
    broadcaster.publish_status("running")
    time.sleep(0.5)

    status_msgs = [m for m in messages if m.topic == f"{topic_base}/status"]
    assert len(status_msgs) >= 1
    status_obj = MInsightStatus.model_validate_json(status_msgs[-1].payload)
    assert status_obj.status == "running"
