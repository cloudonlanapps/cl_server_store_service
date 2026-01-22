"""Singletons for Qdrant vector stores (CLIP, DINO, Face)."""

from __future__ import annotations

from loguru import logger
from qdrant_client.models import Distance

from .qdrant_image_store import QdrantImageStore

_clip_store: QdrantImageStore | None = None
_dino_store: QdrantImageStore | None = None
_face_store: QdrantImageStore | None = None


def get_clip_store(url: str, collection_name: str) -> QdrantImageStore:
    """Get or create the global CLIP QdrantImageStore singleton.

    Args:
        url: Qdrant service URL
        collection_name: Qdrant collection name

    Returns:
        QdrantImageStore singleton instance for CLIP
    """
    global _clip_store

    if _clip_store is not None:
        if _clip_store.url != url or _clip_store.collection_name != collection_name:
            raise RuntimeError(
                f"ClipStore already initialized with different parameters: "
                f"existing(url={_clip_store.url}, col={_clip_store.collection_name}), "
                f"requested(url={url}, col={collection_name})"
            )
        return _clip_store

    _clip_store = QdrantImageStore(
        collection_name=collection_name,
        url=url,
        vector_size=512,  # CLIP embedding dimension
    )
    logger.info(f"Initialized ClipStore: url={url}, collection={collection_name}")

    return _clip_store


def get_dino_store(url: str, collection_name: str) -> QdrantImageStore:
    """Get or create the global DINO QdrantImageStore singleton.

    Args:
        url: Qdrant service URL
        collection_name: Qdrant collection name

    Returns:
        QdrantImageStore singleton instance for DINOv2
    """
    global _dino_store

    if _dino_store is not None:
        if _dino_store.url != url or _dino_store.collection_name != collection_name:
            raise RuntimeError(
                f"DinoStore already initialized with different parameters: "
                f"existing(url={_dino_store.url}, col={_dino_store.collection_name}), "
                f"requested(url={url}, col={collection_name})"
            )
        return _dino_store

    _dino_store = QdrantImageStore(
        collection_name=collection_name,
        url=url,
        vector_size=384,  # DINOv2-S embedding dimension
    )
    logger.info(f"Initialized DinoStore: url={url}, collection={collection_name}")

    return _dino_store


def get_face_store(
    url: str,
    collection_name: str,
    vector_size: int,
) -> QdrantImageStore:
    """Get or create the global face store singleton (separate Qdrant collection).

    Args:
        url: Qdrant service URL
        collection_name: Qdrant collection name
        vector_size: Face embedding vector dimension

    Returns:
        QdrantImageStore singleton instance for face embeddings
    """
    global _face_store

    if _face_store is not None:
        # Check for parameter mismatch (including vector_size if applicable to underlying store)
        if (
            _face_store.url != url
            or _face_store.collection_name != collection_name
            or _face_store._vector_size != vector_size
        ):
            raise RuntimeError(
                f"FaceStore already initialized with different parameters: "
                f"existing(url={_face_store.url}, col={_face_store.collection_name}, size={_face_store._vector_size}), "
                f"requested(url={url}, col={collection_name}, size={vector_size})"
            )
        return _face_store

    _face_store = QdrantImageStore(
        collection_name=collection_name,
        url=url,
        vector_size=vector_size,
        distance=Distance.COSINE,  # For face similarity
    )
    logger.info(f"Initialized Face Store: url={url}, collection={collection_name}")

    return _face_store
