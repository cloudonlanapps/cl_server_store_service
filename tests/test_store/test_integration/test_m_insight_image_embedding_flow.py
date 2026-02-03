import asyncio
import json
import logging
import os
from typing import Any
from pathlib import Path

import pytest
from unittest.mock import patch
from sqlalchemy.orm import sessionmaker

from store.common import StorageService
from store.db_service.db_internals import database
from store.m_insight import MediaInsight
from store.m_insight.config import MInsightConfig
from store.broadcast_service.broadcaster import MInsightBroadcaster, get_insight_broadcaster, reset_broadcaster

import paho.mqtt.client as mqtt
from urllib.parse import urlparse

# Use a longer timeout for local testing if needed
TIMEOUT = 120.0
logger = logging.getLogger(__name__)

@pytest.mark.integration
@pytest.mark.asyncio
async def test_m_insight_image_embedding_flow(
    client: Any, 
    integration_config: Any, 
    test_engine: Any,
    clean_data_dir: Path,
):
    # 0. Clean state
    try:
        import store.vectorstore_services.vector_stores as vs
        vs._clip_store = None
        vs._dino_store = None
        vs._face_store = None
    except (ImportError, AttributeError):
        pass

    # 1. Setup MQTT Listener
    parsed = urlparse(integration_config.mqtt_url)
    mqtt_broker = parsed.hostname
    mqtt_port = parsed.port
    
    if not mqtt_broker or not mqtt_port:
        raise ValueError(f"Invalid MQTT URL: {integration_config.mqtt_url}")
    
    store_port = client.app.state.config.port
    topic_filter = f"mInsight/{store_port}/entity_item_status/+"
    message_queue: asyncio.Queue[tuple[int, str, dict[str, Any]]] = asyncio.Queue()
    
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    loop = asyncio.get_running_loop()
    connected_event = asyncio.Event()
    subscribed_event = asyncio.Event()

    def on_connect(client, userdata, flags, rc, properties):
        loop.call_soon_threadsafe(connected_event.set)

    def on_subscribe(client, userdata, mid, reason_code_list, properties):
        loop.call_soon_threadsafe(subscribed_event.set)

    def on_message(client, userdata, msg):
        try:
            parts = msg.topic.strip("/").split("/")
            entity_id = int(parts[-1])
            payload_str = msg.payload.decode()
            if not payload_str:
                loop.call_soon_threadsafe(message_queue.put_nowait, (entity_id, "CLEARED", {}))
                return

            data = json.loads(payload_str)
            status = data.get("status")
            loop.call_soon_threadsafe(message_queue.put_nowait, (entity_id, status or "unknown", data))
        except Exception:
            pass

    mqtt_client.on_connect = on_connect
    mqtt_client.on_subscribe = on_subscribe
    mqtt_client.on_message = on_message
    
    mqtt_client.connect(mqtt_broker, mqtt_port, 60)
    mqtt_client.loop_start()
    
    await asyncio.wait_for(connected_event.wait(), timeout=5.0)
    mqtt_client.subscribe(topic_filter)
    await asyncio.wait_for(subscribed_event.wait(), timeout=5.0)
    await asyncio.sleep(0.5)

    # 2. Setup Processor
    shared_broadcaster = client.app.state.broadcaster
    if not shared_broadcaster:
        pytest.fail("Broadcaster missing from app state")
    
    min_config = MInsightConfig(
        id="test-worker",
        log_level="DEBUG",
        store_port=store_port,
        mqtt_url=integration_config.mqtt_url,
        mqtt_topic=f"store/{store_port}/items",
        auth_service_url=integration_config.auth_url,
        compute_service_url=integration_config.compute_url,
        qdrant_url=integration_config.qdrant_url,
        cl_server_dir=clean_data_dir,
        media_storage_dir=clean_data_dir / "media",
        public_key_path=clean_data_dir / "keys" / "public_key.pem",
        no_auth=True,
    )
    
    processor = MediaInsight(config=min_config, broadcaster=shared_broadcaster)

    # Prepare Image
    TEST_VECTORS_DIR = Path(os.getenv("TEST_VECTORS_DIR", "/Users/anandasarangaram/Work/cl_server_test_media"))
    image_path = TEST_VECTORS_DIR / "images" / "test_face_single.jpg"
    if not image_path.exists():
        pytest.skip(f"Test image missing: {image_path}")

    # 3. Execution
    try:
        with patch("store.db_service.database.SessionLocal", side_effect=sessionmaker(autocommit=False, autoflush=False, bind=test_engine)):
            (clean_data_dir / "media").mkdir(exist_ok=True, parents=True)

            with open(image_path, "rb") as f:
                files = {"image": ("test_mqtt.jpg", f, "image/jpeg")}
                response = client.post(
                    "/entities", 
                    files=files,
                    data={"label": "MQTT Test Image", "is_collection": False}
                )
            assert response.status_code == 201
            entity_id = response.json()["id"]

            await processor.run_once()

            # Wait for "completed"
            received_statuses = []
            final_payload = None
            
            start_wait = loop.time()
            while (loop.time() - start_wait) < TIMEOUT:
                try:
                    eid, status, payload = await asyncio.wait_for(message_queue.get(), timeout=1.0)
                    if eid != entity_id:
                        continue
                    
                    received_statuses.append(status)
                    if status == "completed":
                        final_payload = payload
                        break
                    if status == "failed":
                        pytest.fail(f"Processing failed: {payload}")
                except asyncio.TimeoutError:
                    continue
                    
            assert "completed" in received_statuses, f"Flow failed. Received: {received_statuses}"
            assert final_payload is not None
            assert final_payload.get("face_detection") == "completed"
            assert final_payload.get("clip_embedding") == "completed"
            assert final_payload.get("dino_embedding") == "completed"
            
    finally:
        await processor.shutdown()
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
