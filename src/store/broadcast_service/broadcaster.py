from __future__ import annotations

import time
from typing import TYPE_CHECKING
from loguru import logger

from cl_ml_tools import BroadcasterBase, get_broadcaster
from .schemas import MInsightStatus
from typing import Any

if TYPE_CHECKING:
    from ..m_insight.config import MInsightConfig
    from .schemas import EntityStatusPayload

_broadcaster: MInsightBroadcaster | None = None


def get_insight_broadcaster(config: MInsightConfig) -> MInsightBroadcaster:
    """Get or create global MInsightBroadcaster singleton."""
    global _broadcaster
    if _broadcaster is not None:
        return _broadcaster

    _broadcaster = MInsightBroadcaster(config)
    _broadcaster.init()
    return _broadcaster


def reset_broadcaster() -> None:
    """Reset the broadcaster singleton (for testing)."""
    global _broadcaster
    if _broadcaster and _broadcaster.broadcaster:
        try:
            _broadcaster.broadcaster.disconnect()
        except Exception:
            pass
    _broadcaster = None


class MInsightBroadcaster:
    """Manages MQTT broadcasting for mInsight process."""

    def __init__(self, config: MInsightConfig):
        self.config: MInsightConfig = config
        self.broadcaster: BroadcasterBase | None = None
        # Resolve port from config (StoreConfig uses 'port', MInsightConfig uses 'store_port')
        port_val = getattr(config, "port", getattr(config, "store_port", 8001))
        try:
            # Handle cases where port might be a Mock or string in tests
            self.port = int(port_val)
        except (ValueError, TypeError):
            self.port = 8001
            
        self.topic_base: str = f"mInsight/{self.port}"
        
        self.current_status: MInsightStatus = MInsightStatus(
            status="unknown",
            timestamp=int(time.time() * 1000)
        )

    def init(self) -> None:
        """Initialize broadcaster."""
        if not self.config.mqtt_url:
            return

        self.broadcaster = get_broadcaster(
            mqtt_url=self.config.mqtt_url,
        )

        # Set LWT
        if self.broadcaster:
            # Heartbeat/Status topic
            status_topic = f"{self.topic_base}/status"
            # LWT payload (offline)
            self.current_status.status = "offline"
            self.current_status.timestamp = int(time.time() * 1000)
            lwt_payload = self.current_status.model_dump_json()
            
            _ = self.broadcaster.set_will(
                topic=status_topic, payload=lwt_payload, qos=1, retain=True
            )

    def _broadcast(self) -> None:
        """Internal helper to publish the current status."""
        if not self.broadcaster:
            return
        topic = f"{self.topic_base}/status"
        self.current_status.timestamp = int(time.time() * 1000)
        _ = self.broadcaster.publish_retained(
            topic=topic, 
            payload=self.current_status.model_dump_json(), 
            qos=1
        )

    def publish_start(self, version_start: int, version_end: int) -> None:
        self.current_status.status = "running"
        self.current_status.version_start = version_start
        self.current_status.version_end = version_end
        self.current_status.processed_count = -1 
        self._broadcast()

    def publish_end(self, processed_count: int) -> None:
        self.current_status.status = "idle"
        self.current_status.processed_count = processed_count
        self._broadcast()

    def publish_status(self, status: str) -> None:
        self.current_status.status = status
        self._broadcast()

    def publish_entity_status(
        self, 
        entity_id: int, 
        payload: EntityStatusPayload, 
        clear_after: float | None = None
    ) -> None:
        """Publish entity status update.
        
        Args:
            entity_id: Entity ID
            payload: EntityStatusPayload object
            clear_after: Optional delay in seconds to clear the message (for final states)
        """
        if not self.broadcaster:
            return

        topic = f"{self.topic_base}/entity_item_status/{entity_id}"
        logger.debug(f"Publishing entity status for {entity_id} to {topic}: {payload.status}")
        _ = self.broadcaster.publish_retained(
            topic=topic,
            payload=payload.model_dump_json(),
            qos=1
        )

        if clear_after:
            import asyncio
            # Schedule cleanup
            # We use asyncio.create_task to run this in background
            # Note: This simple approach assumes the event loop is running.
            # In a real service, we might want more robust task management.
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._delayed_clear(entity_id, clear_after))
            except RuntimeError:
                # No running loop (e.g. sync context), cannot schedule async clear
                pass

    async def _delayed_clear(self, entity_id: int, delay: float) -> None:
        """Wait for delay and then clear the entity status."""
        import asyncio
        await asyncio.sleep(delay)
        self.clear_entity_status(entity_id)

    def clear_entity_status(self, entity_id: int) -> None:
        """Clear the retained status message for an entity."""
        if not self.broadcaster:
            return

        topic = f"{self.topic_base}/entity_item_status/{entity_id}"
        # Publish empty retained message to clear it
        _ = self.broadcaster.publish_retained(
            topic=topic,
            payload="",
            qos=1
        )

    def publish_event(self, topic: str, payload: str, qos: int = 1) -> Any:
        """Wrapper for internal broadcaster publish_event."""
        if self.broadcaster:
            return self.broadcaster.publish_event(topic=topic, payload=payload, qos=qos)
        return None

    def publish_retained(self, topic: str, payload: str, qos: int = 1) -> Any:
        """Wrapper for internal broadcaster publish_retained."""
        if self.broadcaster:
            return self.broadcaster.publish_retained(topic=topic, payload=payload, qos=qos)
        return None
