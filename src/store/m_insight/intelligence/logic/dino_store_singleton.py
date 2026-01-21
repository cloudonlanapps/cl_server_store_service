"""Singleton QdrantImageStore for DINOv2 embeddings."""

from __future__ import annotations

from loguru import logger

from .pysdk_config import PySDKRuntimeConfig
from .qdrant_image_store import QdrantImageStore

_dino_store: QdrantImageStore | None = None


def get_dino_store(config: PySDKRuntimeConfig | None = None) -> QdrantImageStore:
    """Get or create the global DINO QdrantImageStore singleton.

    Args:
        config: PySDK runtime configuration (required on first call, optional afterwards)

    Returns:
        QdrantImageStore singleton instance for DINOv2

    Raises:
        RuntimeError: If called before initialization without config
    """
    global _dino_store

    if _dino_store is None:
        if config is None:
            raise RuntimeError(
                "DinoStore not initialized. Pass config on first call."
            )
        _dino_store = QdrantImageStore(
            collection_name=f"{config.qdrant_collection_name}_dino",
            url=config.qdrant_url,
            vector_size=384,  # DINOv2-S embedding dimension
        )
        logger.info(f"Initialized DinoStore: url={config.qdrant_url}, collection={config.qdrant_collection_name}_dino")

    return _dino_store
