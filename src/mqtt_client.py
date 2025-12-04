"""MQTT Client for worker capability discovery and management."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Optional

import paho.mqtt.client as mqtt

from .config import CAPABILITY_CACHE_TIMEOUT, CAPABILITY_TOPIC_PREFIX, MQTT_BROKER, MQTT_PORT

logger = logging.getLogger(__name__)

_mqtt_client_instance: Optional[MQTTClient] = None
_mqtt_lock = threading.Lock()


class MQTTClient:
    """MQTT client for subscribing to worker capability messages.

    Maintains a cache of worker capabilities from MQTT retained messages.
    Provides methods to query aggregated capabilities by task type.
    """

    def __init__(self, broker: str = MQTT_BROKER, port: int = MQTT_PORT):
        """Initialize MQTT client.

        Args:
            broker: MQTT broker hostname
            port: MQTT broker port
        """
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.capabilities_cache: dict = {}  # {"worker_id": {...message}}
        self.cache_lock = threading.Lock()
        self.connected = False
        self.ready_event = threading.Event()

        # Setup callbacks
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        self._connect()

    def _connect(self):
        """Connect to MQTT broker."""
        try:
            logger.info(f"Connecting to MQTT broker at {self.broker}:{self.port}")
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")

    def _on_connect(self, client, userdata, connect_flags, reason_code, properties):
        """Callback for MQTT connection."""
        if reason_code == 0:
            logger.info("Connected to MQTT broker")
            self.connected = True
            # Subscribe to worker capability topics
            topic = f"{CAPABILITY_TOPIC_PREFIX}/+"
            client.subscribe(topic, qos=1)
            logger.info(f"Subscribed to {topic}")
            # Signal that client is ready
            self.ready_event.set()
        else:
            logger.error(f"Failed to connect to MQTT broker: {reason_code}")
            self.connected = False

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        """Callback for MQTT disconnection."""
        logger.warning(f"Disconnected from MQTT broker: {reason_code}")
        self.connected = False
        self.ready_event.clear()

    def _on_message(self, client, userdata, msg):
        """Callback for incoming MQTT messages."""
        try:
            topic = msg.topic
            payload = msg.payload.decode("utf-8")

            # Extract worker_id from topic (e.g., "inference/workers/worker-1")
            parts = topic.split("/")
            if len(parts) < 3:
                logger.warning(f"Invalid topic format: {topic}")
                return

            worker_id = parts[-1]

            # Handle empty payload (LWT cleanup message)
            if not payload or payload.strip() == "":
                logger.info(f"Worker {worker_id} disconnected (LWT message)")
                with self.cache_lock:
                    self.capabilities_cache.pop(worker_id, None)
                return

            # Parse capability message
            try:
                data = json.loads(payload)
                with self.cache_lock:
                    self.capabilities_cache[worker_id] = data
                logger.debug(f"Updated capabilities for {worker_id}: {data}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse capability message from {worker_id}: {e}")
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")

    def get_cached_capabilities(self) -> dict:
        """Get aggregated idle counts by capability.

        Returns:
            Dict mapping capability names to total idle count
            Example: {"image_resize": 2, "image_conversion": 1}
        """
        aggregated = {}

        with self.cache_lock:
            for worker_id, data in self.capabilities_cache.items():
                if not isinstance(data, dict):
                    continue

                capabilities = data.get("capabilities", [])
                idle_count = data.get("idle_count", 0)

                for capability in capabilities:
                    if capability not in aggregated:
                        aggregated[capability] = 0
                    aggregated[capability] += idle_count

        return aggregated

    def wait_for_capabilities(self, timeout: int = CAPABILITY_CACHE_TIMEOUT) -> bool:
        """Wait for MQTT client to be ready and receive initial messages.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if ready, False if timeout
        """
        return self.ready_event.wait(timeout=timeout)

    def get_worker_count_by_capability(self) -> dict:
        """Get total worker count by capability (not idle count).

        Returns:
            Dict mapping capability names to total worker count
            Example: {"image_resize": 2, "image_conversion": 2}
        """
        total_workers = {}

        with self.cache_lock:
            for worker_id, data in self.capabilities_cache.items():
                if not isinstance(data, dict):
                    continue

                capabilities = data.get("capabilities", [])

                for capability in capabilities:
                    if capability not in total_workers:
                        total_workers[capability] = 0
                    total_workers[capability] += 1

        return total_workers

    def disconnect(self):
        """Disconnect from MQTT broker and stop loop."""
        try:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("Disconnected from MQTT broker")
        except Exception as e:
            logger.error(f"Error disconnecting from MQTT broker: {e}")


def get_mqtt_client() -> MQTTClient:
    """Get or create singleton MQTT client instance."""
    global _mqtt_client_instance

    if _mqtt_client_instance is None:
        with _mqtt_lock:
            if _mqtt_client_instance is None:
                _mqtt_client_instance = MQTTClient(broker=MQTT_BROKER, port=MQTT_PORT)
    return _mqtt_client_instance


def close_mqtt_client():
    """Close the MQTT client singleton."""
    global _mqtt_client_instance

    if _mqtt_client_instance is not None:
        _mqtt_client_instance.disconnect()
        _mqtt_client_instance = None
