
import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


def test_mqtt_broadcast_on_create(client: TestClient, sample_image: Path):
    """Test that MQTT event is broadcasted on successful media creation."""
    # Setup mock broadcaster
    mock_broadcaster = MagicMock()
    client.app.state.broadcaster = mock_broadcaster

    # Perform POST
    with open(sample_image, "rb") as f:
        response = client.post(
            "/entities",
            data={
                "is_collection": "false",
                "label": "Test Image"
            },
            files={"image": ("test.jpg", f, "image/jpeg")}
        )

    assert response.status_code == 201
    item = response.json()

    # Verify broadcast
    config = client.app.state.config
    expected_topic = f"store/{config.port}/items"

    assert mock_broadcaster.publish_event.called
    args, kwargs = mock_broadcaster.publish_event.call_args
    assert kwargs["topic"] == expected_topic

    payload = json.loads(kwargs["payload"])
    assert payload["id"] == item["id"]
    assert payload["md5"] == item["md5"]
    assert "timestamp" in payload

def test_mqtt_broadcast_on_update(client: TestClient, sample_image: Path, sample_images: list[Path]):
    """Test that MQTT event is broadcasted on successful media update."""
    # 1. Create first
    with open(sample_image, "rb") as f:
        response = client.post(
            "/entities",
            data={"is_collection": "false", "label": "Original"},
            files={"image": ("orig.jpg", f, "image/jpeg")}
        )
    item = response.json()
    entity_id = item["id"]

    # Setup mock broadcaster for UPDATE
    mock_broadcaster = MagicMock()
    client.app.state.broadcaster = mock_broadcaster

    # 2. Perform PUT with DIFFERENT image to ensure MD5 changes/triggers event
    # (The requirement says: broadcast when existing media item's file is replaced)
    with open(sample_images[1], "rb") as f:
        response = client.put(
            f"/entities/{entity_id}",
            data={"is_collection": "false", "label": "Updated"},
            files={"image": ("updated.jpg", f, "image/jpeg")}
        )

    assert response.status_code == 200
    updated_item = response.json()

    # Verify broadcast
    config = client.app.state.config
    expected_topic = f"store/{config.port}/items"
    assert mock_broadcaster.publish_event.called
    _, kwargs = mock_broadcaster.publish_event.call_args
    assert kwargs["topic"] == expected_topic

    payload = json.loads(kwargs["payload"])
    assert payload["id"] == entity_id
    assert payload["md5"] == updated_item["md5"]
    assert payload["md5"] != item["md5"]

@pytest.fixture
def mqtt_config(request):
    return {
        "server": request.config.getoption("--mqtt-server"),
        "port": request.config.getoption("--mqtt-port"),
    }

def test_mqtt_real_broadcast_create(client: TestClient, sample_image: Path, mqtt_config):
    """Integration test with a real MQTT service for POST (Create)."""
    if not mqtt_config["port"]:
        pytest.skip("Real MQTT broker not configured")

    import threading

    import paho.mqtt.client as mqtt
    from paho.mqtt.enums import CallbackAPIVersion

    config = client.app.state.config
    mqtt_broker = mqtt_config["server"]
    mqtt_port = mqtt_config["port"]
    topic = f"store/{config.port}/items"

    events_received = []
    connect_event = threading.Event()

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            client.subscribe(topic)
            connect_event.set()

    def on_message(client, userdata, msg):
        events_received.append(msg.payload.decode())

    subscriber = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=f"test_sub_create_{int(time.time_ns())}")
    subscriber.on_connect = on_connect
    subscriber.on_message = on_message

    subscriber.connect(mqtt_broker, mqtt_port)
    subscriber.loop_start()

    try:
        # Wait for connection and subscription
        if not connect_event.wait(timeout=5):
            pytest.fail("Failed to connect to MQTT broker")

        # Perform POST
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities",
                data={"is_collection": "false", "label": "Real MQTT Test Create"},
                files={"image": ("real_test_create.jpg", f, "image/jpeg")}
            )
        assert response.status_code == 201
        item = response.json()

        # Wait for message
        start_time = time.time()
        while len(events_received) == 0 and (time.time() - start_time) < 5:
            time.sleep(0.1)

        assert len(events_received) > 0, "No MQTT message received"
        received_payload = json.loads(events_received[0])
        assert received_payload["id"] == item["id"]
        assert received_payload["md5"] == item["md5"]
        assert "timestamp" in received_payload

    finally:
        subscriber.loop_stop()
        subscriber.disconnect()

def test_mqtt_real_broadcast_update(client: TestClient, sample_images: list[Path], mqtt_config):
    """Integration test with a real MQTT service for PUT (Update)."""
    if not mqtt_config["port"]:
        pytest.skip("Real MQTT broker not configured")

    # 1. Create initial entity
    with open(sample_images[0], "rb") as f:
        response = client.post(
            "/entities",
            data={"is_collection": "false", "label": "Real MQTT Test Update"},
            files={"image": ("real_test_orig.jpg", f, "image/jpeg")}
        )
    item = response.json()
    entity_id = item["id"]

    import threading

    import paho.mqtt.client as mqtt
    from paho.mqtt.enums import CallbackAPIVersion

    config = client.app.state.config
    mqtt_broker = mqtt_config["server"]
    mqtt_port = mqtt_config["port"]
    topic = f"store/{config.port}/items"

    events_received = []
    connect_event = threading.Event()

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            client.subscribe(topic)
            connect_event.set()

    def on_message(client, userdata, msg):
        events_received.append(msg.payload.decode())

    subscriber = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=f"test_sub_update_{int(time.time_ns())}")
    subscriber.on_connect = on_connect
    subscriber.on_message = on_message

    subscriber.connect(mqtt_broker, mqtt_port)
    subscriber.loop_start()

    try:
        # Wait for connection and subscription
        if not connect_event.wait(timeout=5):
            pytest.fail("Failed to connect to MQTT broker")

        # 2. Perform PUT with DIFFERENT image
        with open(sample_images[1], "rb") as f:
            response = client.put(
                f"/entities/{entity_id}",
                data={"is_collection": "false", "label": "Real MQTT Test Updated"},
                files={"image": ("real_test_updated.jpg", f, "image/jpeg")}
            )
        assert response.status_code == 200
        updated_item = response.json()

        # Wait for message
        start_time = time.time()
        while len(events_received) == 0 and (time.time() - start_time) < 5:
            time.sleep(0.1)

        assert len(events_received) > 0, f"No MQTT message received. Checked for {(time.time() - start_time):.2f}s"
        received_payload = json.loads(events_received[0])
        # The update might result in a new ID (e.g. if implementation does copy-on-write or similar),
        # so we should check against the ID returned by the PUT response.
        assert received_payload["id"] == updated_item["id"]
        assert received_payload["md5"] == updated_item["md5"]
        assert received_payload["md5"] != item["md5"]

    finally:
        subscriber.loop_stop()
        subscriber.disconnect()
