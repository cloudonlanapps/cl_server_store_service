from __future__ import annotations

import time
from typing import TYPE_CHECKING

from cl_ml_tools import BroadcasterBase

if TYPE_CHECKING:
    from .config import MInsightConfig
    from .schemas import MInsightStatus


class MInsightBroadcaster:
    """Manages MQTT broadcasting for mInsight process."""

    def __init__(self, config: MInsightConfig):
        self.config: MInsightConfig = config
        self.broadcaster: BroadcasterBase | None = None
        self.port: int = config.store_port
        self.topic_base: str = f"mInsight/{self.port}"
        from .schemas import MInsightStatus
        self.current_status: MInsightStatus = MInsightStatus(
            port=self.port,
            status="unknown",
            timestamp=int(time.time() * 1000)
        )

    def init(self) -> None:
        """Initialize broadcaster."""
        if not self.config.mqtt_port:
            return

        from cl_ml_tools import get_broadcaster

        self.broadcaster = get_broadcaster(
            broadcast_type="mqtt",
            broker=self.config.mqtt_broker,
            port=self.config.mqtt_port,
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
        self.current_status.processed_count = -1 # doesn't make sense to preserve last processed_count
        self._broadcast()

    def publish_end(self, processed_count: int) -> None:
        self.current_status.status = "idle"
        self.current_status.processed_count = processed_count
        self._broadcast()

    def publish_status(self, status: str) -> None:
        self.current_status.status = status
        self._broadcast()
