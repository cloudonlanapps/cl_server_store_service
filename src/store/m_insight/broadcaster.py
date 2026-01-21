from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import MInsightConfig


class MInsightBroadcaster:
    """Manages MQTT broadcasting for mInsight process."""

    def __init__(self, config: MInsightConfig):
        self.config = config
        self.broadcaster = None
        self.port = config.server_port
        self.topic_base = f"mInsight/{self.port}"

    def init(self):
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
            # LWT payload
            lwt_payload = self._create_status_payload("offline").model_dump_json()
            _ = self.broadcaster.set_will(topic=status_topic, payload=lwt_payload, qos=1, retain=True)

    def _create_status_payload(self, status: str):
        from .models import MInsightStatusPayload
        return MInsightStatusPayload(status=status, timestamp=int(time.time() * 1000))

    def publish_start(self, version_start: int, version_end: int):
        if not self.broadcaster:
            return
        from .models import MInsightStartPayload

        topic = f"{self.topic_base}/started"
        payload = MInsightStartPayload(
            version_start=version_start,
            version_end=version_end,
            timestamp=int(time.time() * 1000)
        )
        self.broadcaster.publish_event(topic=topic, payload=payload.model_dump_json())

    def publish_end(self, processed_count: int):
        if not self.broadcaster:
            return
        from .models import MInsightStopPayload

        topic = f"{self.topic_base}/ended"
        payload = MInsightStopPayload(
            processed_count=processed_count,
            timestamp=int(time.time() * 1000)
        )
        self.broadcaster.publish_event(topic=topic, payload=payload.model_dump_json())

    def publish_status(self, status: str):
        if not self.broadcaster:
            return
        topic = f"{self.topic_base}/status"
        payload = self._create_status_payload(status)
        self.broadcaster.publish_retained(topic=topic, payload=payload.model_dump_json(), qos=1)
