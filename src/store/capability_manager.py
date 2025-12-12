"""Worker capability discovery and management using cl_ml_tools broadcaster."""

from __future__ import annotations

import json
import logging
import threading
from typing import Dict, Optional

from cl_ml_tools import get_broadcaster
from cl_server_shared.config import Config

logger = logging.getLogger(__name__)

_capability_manager_instance: Optional[CapabilityManager] = None
_manager_lock = threading.Lock()


class CapabilityManager:
    """Manages worker capability discovery using cl_ml_tools broadcaster.

    This class replaces the custom MQTTClient implementation with the
    standardized broadcaster from cl_ml_tools. It maintains the same
    external interface for backward compatibility.

    Key differences from MQTTClient:
    - Uses get_broadcaster() instead of paho-mqtt directly
    - Relies on cl_ml_tools for connection management
    - Same caching and aggregation logic
    """

    def __init__(self):
        """Initialize capability manager with broadcaster."""
        self.capabilities_cache: Dict[str, dict] = {}
        self.cache_lock = threading.Lock()
        self.ready_event = threading.Event()

        # Get broadcaster from cl_ml_tools
        self.broadcaster = get_broadcaster(
            broadcast_type=Config.BROADCAST_TYPE,
            broker=Config.MQTT_BROKER,
            port=Config.MQTT_PORT,
        )

        # Subscribe to worker capability topics
        topic_pattern = f"{Config.CAPABILITY_TOPIC_PREFIX}/+"
        self.broadcaster.subscribe(
            topic=topic_pattern,
            callback=self._on_message
        )

        logger.info(f"Subscribed to capability topics: {topic_pattern}")
        self.ready_event.set()

    def _on_message(self, topic: str, payload: str):
        """Callback for incoming capability messages.

        Args:
            topic: MQTT topic (e.g., "inference/workers/worker-1")
            payload: JSON string with worker capabilities
        """
        try:
            # Extract worker_id from topic
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
                logger.error(
                    f"Failed to parse capability message from {worker_id}: {e}"
                )
        except Exception as e:
            logger.error(f"Error processing capability message: {e}")

    def get_cached_capabilities(self) -> Dict[str, int]:
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

    def wait_for_capabilities(
        self, timeout: int = Config.CAPABILITY_CACHE_TIMEOUT
    ) -> bool:
        """Wait for capability manager to be ready.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if ready, False if timeout
        """
        return self.ready_event.wait(timeout=timeout)

    def get_worker_count_by_capability(self) -> Dict[str, int]:
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
        """Disconnect from broadcaster."""
        try:
            if self.broadcaster:
                self.broadcaster.disconnect()
            logger.info("Disconnected from broadcaster")
        except Exception as e:
            logger.error(f"Error disconnecting from broadcaster: {e}")


def get_capability_manager() -> CapabilityManager:
    """Get or create singleton CapabilityManager instance."""
    global _capability_manager_instance

    if _capability_manager_instance is None:
        with _manager_lock:
            if _capability_manager_instance is None:
                _capability_manager_instance = CapabilityManager()
    return _capability_manager_instance


def close_capability_manager():
    """Close the CapabilityManager singleton."""
    global _capability_manager_instance

    if _capability_manager_instance is not None:
        _capability_manager_instance.disconnect()
        _capability_manager_instance = None
