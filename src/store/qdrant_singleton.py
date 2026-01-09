"""Singleton QdrantImageStore for the store service."""

from __future__ import annotations

import logging

from .pysdk_config import PySDKRuntimeConfig
from .qdrant_image_store import QdrantImageStore

logger = logging.getLogger(__name__)

_qdrant_store: QdrantImageStore | None = None


def get_qdrant_store(config: PySDKRuntimeConfig | None = None) -> QdrantImageStore:
    """Get or create the global QdrantImageStore singleton.

    Args:
        config: PySDK runtime configuration (required on first call, optional afterwards)

    Returns:
        QdrantImageStore singleton instance

    Raises:
        RuntimeError: If called before initialization without config
    """
    global _qdrant_store

    if _qdrant_store is None:
        if config is None:
            raise RuntimeError(
                "QdrantImageStore not initialized. Pass config on first call "
                "(typically done in FastAPI startup event)."
            )
        _qdrant_store = QdrantImageStore(
            collection_name=config.qdrant_collection_name,
            url=config.qdrant_url,
            vector_size=512,  # CLIP embedding dimension
            logger=logger,
        )
        logger.info(f"Initialized QdrantImageStore: url={config.qdrant_url}")

    return _qdrant_store
