from ..common.config import BaseConfig

# Face embedding dimension constant (determined by ArcFace model)
FACE_VECTOR_SIZE = 512


class MInsightConfig(BaseConfig):
    """Unified mInsight configuration and CLI arguments."""

    # CLI Fields (mapped to Args)
    id: str
    log_level: str
    store_port: int

    # External Service URLs
    auth_url: str
    compute_url: str
    compute_username: str
    compute_password: str

    # MQTT configuration
    mqtt_topic: str
