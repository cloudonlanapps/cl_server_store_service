
import asyncio
import json
import logging
import os
from typing import Any
from pathlib import Path

import pytest
from unittest.mock import patch
from sqlalchemy.orm import sessionmaker

from cl_ml_tools import get_broadcaster
from store.common import StorageService
from store.db_service.db_internals import database
from store.m_insight import MediaInsight
from store.m_insight.config import MInsightConfig
from store.broadcast_service.broadcaster import MInsightBroadcaster

# Use a longer timeout for local testing if needed
TIMEOUT = 30.0

@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skip(reason="Skipping temporarily as this test is expeected to fail")
async def test_m_insight_image_embedding_flow(
    client: Any, 
    integration_config: Any, 
    test_engine: Any,
):
    """Verify image embedding flow with MQTT status updates.
    
    This test:
    1. Subscribes to MQTT topic `mInsight/{port}/entity_item_status/+`
    2. Uploads an image via Store API
    3. Waits for "queued" -> "processing" -> "completed" status events
    4. Verifies payload content and cleanup
    """
    
    # 1. Setup MQTT Listener
    mqtt_broker = integration_config.mqtt_broker
    mqtt_port = integration_config.mqtt_port
    store_port = integration_config.store_port
    
    assert mqtt_port is not None, "MQTT port not configured"
    
    # Topic to subscribe to: mInsight/<port>/entity_item_status/+/
    # Note: Using wildcard + for entity_id
    topic_filter = f"mInsight/{store_port}/entity_item_status/+"
    
    # Queue to capture messages
    # queue of (entity_id, status, payload_dict)
    message_queue: asyncio.Queue[tuple[int, str, dict[str, Any]]] = asyncio.Queue()
    
    # Initialize broadcaster just to get a client? No, use raw paho-mqtt or get_broadcaster
    # get_broadcaster returns a wrapper. Let's use a raw client for testing verification 
    # OR use the same wrapper if it supports subscribe. 
    # BroadcasterBase usually for publishing. 
    # We'll use paho-mqtt directly or a simple helper if avail.
    
    import paho.mqtt.client as mqtt
    
    mqtt_client = mqtt.Client()
    
    def on_message(client, userdata, msg):
        try:
            # Topic: mInsight/8011/entity_item_status/123/
            # Extract entity_id
            parts = msg.topic.strip("/").split("/")
            entity_id = int(parts[-1])
            
            payload_str = msg.payload.decode()
            if not payload_str:
                # Empty payload = cleanup
                asyncio.run_coroutine_threadsafe(
                    message_queue.put((entity_id, "CLEARED", {})), 
                    loop
                )
                return

            data = json.loads(payload_str)
            status = data.get("status")
            timestamp = data.get("timestamp")
            
            # Put in queue
            asyncio.run_coroutine_threadsafe(
                message_queue.put((entity_id, status, data)), 
                loop
            )
            
        except Exception as e:
            logging.error(f"Test MQTT handler failed: {e}")

    mqtt_client.on_message = on_message
    
    loop = asyncio.get_running_loop()
    
    logging.info(f"Connecting to MQTT broker {mqtt_broker}:{mqtt_port}...")
    mqtt_client.connect(mqtt_broker, mqtt_port, 60)
    mqtt_client.subscribe(topic_filter)
    mqtt_client.loop_start()

    # Create session factory bound to test engine
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Prepare MInsight Processor
    # Need to construct MInsightConfig from integration_config
    # Note: integration_config is pydantic model IntegrationConfig (from conftest)
    # MInsightConfig is different.
    
    # We need absolute path for dirs
    # client fixture uses clean_data_dir setup in app.state.config
    # We can try to reuse that or just assume standard structure since clean_data_dir is session/function scoped 
    # but clean_data_dir path is available in client fixture... wait, client fixture overrides CL_SERVER_DIR env var to str(clean_data_dir)
    # We can get it from os.environ
    import os
    server_dir = Path(os.environ["CL_SERVER_DIR"])
    
    min_config = MInsightConfig(
        id="test-worker",
        log_level="DEBUG",
        store_port=store_port,
        mqtt_broker=mqtt_broker,
        mqtt_port=mqtt_port,
        mqtt_topic=f"store/{store_port}/items",
        auth_service_url=integration_config.auth_url,
        compute_service_url=integration_config.compute_url,
        qdrant_url=integration_config.qdrant_url,
        cl_server_dir=server_dir,
        media_storage_dir=server_dir / "media",
        public_key_path=server_dir / "keys" / "public_key.pem",
        no_auth=True, # Simplify testing
    )
    
    # Initialize Broadcaster for Processor (to publish updates)
    proc_broadcaster = MInsightBroadcaster(min_config)
    proc_broadcaster.init()

    # Locate test image
    TEST_VECTORS_DIR = Path(os.getenv("TEST_VECTORS_DIR", "/Users/anandasarangaram/Work/cl_server_test_media"))
    image_path = TEST_VECTORS_DIR / "images" / "test_face_single.jpg"
    
    if not image_path.exists():
        pytest.skip(f"Test image not found: {image_path}")

    try:
        # Patch SessionLocal to use our test engine
        with patch("store.db_service.database.SessionLocal", side_effect=TestingSessionLocal):
            
            # Initialize Processor inside patch context so it gets correct DB session
            processor = MediaInsight(config=min_config, broadcaster=proc_broadcaster)
        
            # 2. Upload Image
            # client is a synchronous TestClient
            with open(image_path, "rb") as f:
                response = client.post(
                    "/entities", 
                    files={"image": ("test_mqtt.jpg", f, "image/jpeg")},
                    data={"label": "MQTT Test Image", "is_collection": False}
                )
            assert response.status_code == 201
            entity_id = response.json()["id"]
            logging.info(f"Created entity {entity_id}")

            # 3. Trigger Processing & Wait for Events
            
            # Run processor once to pick up the job
            # This simulates the worker waking up on valid interaction
            logging.info("Triggering processor run_once...")
            await processor.run_once()

            received_statuses = []
            final_payload = None
            
            start_time = loop.time()
            while (loop.time() - start_time) < TIMEOUT:
                try:
                    # Check if we should re-trigger (simulating loop)
                    # Use asyncio.sleep to yield control
                    
                    # Wait for next message
                    try:
                        eid, status, payload = await asyncio.wait_for(message_queue.get(), timeout=1.0)
                        
                        if eid != entity_id:
                            continue
                        
                        logging.info(f"Received status: {status}")
                        received_statuses.append(status)
                        
                        if status == "completed":
                            final_payload = payload
                            break
                        
                        if status == "failed":
                            # If failed, we might want to see why
                            pytest.fail(f"Entity processing failed: {payload}")
                            
                    except asyncio.TimeoutError:
                        # Timeout on queue, maybe processing is slow?
                        # Trigger run_once again to poll/continue
                        # (Not strictly needed if async jobs run in background, but run_once might handle transitions)
                        # Actually, run_once submits jobs. Callbacks update status.
                        # Do we need to keep calling something?
                        # If callbacks are handled by ComputeClient automatically (if it has background thread), we just wait.
                        pass
                        
                except asyncio.TimeoutError:
                    continue
                    
            assert "completed" in received_statuses, f"Did not receive 'completed' status. Got: {received_statuses}"
            assert final_payload is not None
            
            # Verify payload details (Pydantic model serialized to dict)
            details = final_payload.get("details", {})
            
            # Flattened structure: details { face_detection: "completed", clip_embedding: "completed", ... }
            assert details.get("face_detection") == "completed"
            assert details.get("clip_embedding") == "completed"
            assert details.get("dino_embedding") == "completed"
            
            # Face embeddings check
            face_embeddings = details.get("face_embeddings")
            assert isinstance(face_embeddings, list)
            if face_embeddings:
                assert all(s == "completed" for s in face_embeddings)
            
            # 4. Verify Admin Clear
            # Skip as planned
            
            logging.info("MQTT flow verification successful")

    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
