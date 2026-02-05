"""Singletons for Qdrant vector stores (CLIP, DINO, Face)."""

from __future__ import annotations

import io
from typing import cast, override

import numpy as np
from fastapi import Depends
from loguru import logger
from numpy.typing import NDArray
from qdrant_client import QdrantClient
from qdrant_client.http.models import HnswConfigDiff, PointStruct
from qdrant_client.models import (
    Distance,
    OptimizersConfigDiff,
    PointIdsList,
    Record,
    ScoredPoint,
    StrictFloat,
    StrictInt,
    VectorParams,
    VectorStructOutput,
)

from store.m_insight.config import FACE_VECTOR_SIZE
from store.store.config import StoreConfig

from .exceptions import VectorResourceNotFound
from .schemas import SearchPreferences, SearchResult, StoreItem


class StoreInterface[StoreItemT, SearchOptionsT, SearchResultT]:
    """
    Abstract base class for a generic vector store interface.

    This class defines a standard interface for interacting with a vector store,
    allowing for different underlying implementations (e.g., Qdrant, Milvus, FAISS).
    Subclasses must implement methods for adding, retrieving, deleting, and searching vectors.
    """

    def add_vector(self, item: StoreItemT) -> int:
        """
        Adds a single vector to the store with a given ID and optional payload.
        """
        _ = item
        raise NotImplementedError

    def get_vector(self, id: int) -> StoreItemT | None:
        """
        Retrieves a vector by its ID.
        """
        _ = id
        raise NotImplementedError

    def get_vector_buffer(self, id: int) -> io.BytesIO:
        """
        Retrieves a vector by its ID and returns it as a BytesIO buffer of .npy data.
        """
        point = self.get_vector(id=id)
        if not point:
            raise VectorResourceNotFound(f"Vector {id} not found in vector store")

        buffer = io.BytesIO()
        np.save(buffer, point.embedding)
        _ = buffer.seek(0)
        return buffer

    def delete_vector(self, id: int) -> None:
        """
        Deletes a vector by its ID.
        """
        _ = id
        raise NotImplementedError

    def search(
        self,
        query_vector: NDArray[np.float32],
        limit: int = 5,
        search_options: SearchOptionsT | None = None,
    ) -> list[SearchResultT]:
        """
        Searches for similar vectors in the store.
        """
        _ = query_vector
        _ = limit
        _ = search_options
        raise NotImplementedError


class QdrantVectorStore(StoreInterface[StoreItem, SearchPreferences, SearchResult]):
    """
    Manages image vectors in a Qdrant collection.

    This class provides an interface to interact with Qdrant, handling
    collection creation, adding new image embeddings, retrieving, deleting,
    and performing similarity searches. It ensures that the Qdrant collection
    is properly configured for efficient vector storage and retrieval.
    """

    def __init__(
        self,
        collection_name: str,
        url: str,
        vector_size: int = 512,
        distance: Distance = Distance.COSINE,
        hnsw_m: int = 16,
        hnsw_ef_construct: int = 200,
        max_segment_size: int = 100000,
    ):
        """
        Initialize the Qdrant image vector store, creating the collection if missing.
        """
        self.collection_name: str = collection_name
        self.client: QdrantClient = QdrantClient(url)
        self.url: str = url
        self.vector_size: int = vector_size  # Store for singleton check

        vector_params = VectorParams(size=vector_size, distance=distance)
        hnsw_params = HnswConfigDiff(m=hnsw_m, ef_construct=hnsw_ef_construct)
        optimizer_params: OptimizersConfigDiff = OptimizersConfigDiff.model_validate(
            {"max_segment_size": max_segment_size}
        )
        self.vector_params: VectorParams = vector_params

        if not self.client.collection_exists(collection_name=collection_name):
            logger.debug(f"Creating collection: {collection_name}")
            _ = self.client.create_collection(
                collection_name=collection_name,
                vectors_config=vector_params,
                hnsw_config=hnsw_params,
                optimizers_config=optimizer_params,
            )
        else:
            logger.debug(f"Collection '{collection_name}' already exists. Reusing it.")
            existing = self.client.get_collection(collection_name=collection_name)
            existing_params = existing.config.params.vectors
            if existing_params and isinstance(existing_params, VectorParams):
                if (
                    existing_params.size != vector_params.size
                    or existing_params.distance.value != vector_params.distance.value
                ):
                    logger.error("Collection config differs from expected parameters!")
                    logger.error(
                        f"Existing size: {existing_params.size}, distance: {existing_params.distance}"
                    )
                    logger.error(
                        f"Expected size: {vector_params.size}, distance: {vector_params.distance}"
                    )
                    raise ValueError("Collection config mismatch.")
            elif existing_params:
                raise ValueError("Failed to retrieve collection parameters .")
            else:
                raise ValueError(
                    "Collection config mismatch. Multi vector collection not supported."
                )

    # ---------------------------------------------------------------------

    def _to_qdrant_vector(self, embedding: NDArray[np.float32]) -> list[StrictFloat]:
        if embedding.ndim != 1:
            raise ValueError("Embedding must be 1D")

        if embedding.shape[0] != self.vector_params.size:
            raise ValueError(
                f"Expected embedding of size {self.vector_params.size}, got {embedding.shape[0]}"
            )

        return cast(list[StrictFloat], embedding.tolist())

    def _to_embedding(self, qdrant_vector: VectorStructOutput) -> NDArray[np.float32]:
        if len(qdrant_vector) != self.vector_params.size:
            raise ValueError(
                f"Expected embedding of size {self.vector_params.size}, got {len(qdrant_vector)}"
            )
        return np.array(qdrant_vector, dtype=np.float32)

    @override
    def add_vector(self, item: StoreItem) -> int:
        """
        Add or update a single image vector to Qdrant.
        """

        point = PointStruct(
            id=item.id,
            vector=self._to_qdrant_vector(item.embedding),
            payload=item.payload,
        )

        _ = self.client.upsert(collection_name=self.collection_name, points=[point])
        logger.info(f"Upserted vector {item.id} into collection '{self.collection_name}'")
        return True

    # ---------------------------------------------------------------------
    @override
    def get_vector(self, id: int) -> StoreItem | None:
        """
        Retrieve a point from Qdrant using the deterministic path-based ID.
        """

        records: list[Record] = self.client.retrieve(
            collection_name=self.collection_name, ids=[id], with_vectors=True
        )
        if records:
            point: Record = records[0]
            if point.vector:
                return StoreItem(
                    id=cast(StrictInt, point.id),
                    embedding=self._to_embedding(point.vector),
                    payload=point.payload if point.payload else None,
                )
        return None

    # ---------------------------------------------------------------------
    @override
    def delete_vector(self, id: int):
        """
        Delete a point based on its deterministic path-based ID.
        """
        _ = self.client.delete(
            collection_name=self.collection_name,
            points_selector=PointIdsList.model_validate({"points": [id]}),
        )

        logger.debug(f"Deleted: {id}")

    # ---------------------------------------------------------------------
    @override
    def search(
        self,
        query_vector: NDArray[np.float32],
        limit: int = 5,
        search_options: SearchPreferences | None = None,
    ) -> list[SearchResult]:
        """
        Search for similar vectors in the collection.

        Args:
            query_vector: The query embedding (float32 list or numpy array)
            limit: Number of nearest neighbors to return
            with_payload: Whether to return payload (metadata) along with results

        Returns:
            List of search results with (id, score, payload)
        """
        results: list[ScoredPoint] = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit,
            score_threshold=search_options.score_threshold if search_options else None,
            with_payload=search_options.with_payload if search_options else True,
            with_vectors=search_options.with_vectors if search_options else True,
        ).points

        search_results: list[SearchResult] = []
        for r in results:
            if r.vector is not None:
                # Clamp score to [0.0, 1.0] to handle floating-point precision errors
                # Cosine similarity can sometimes return values slightly > 1.0 (e.g., 1.0000001)
                clamped_score = max(0.0, min(1.0, r.score))
                search_results.append(
                    SearchResult.model_validate(
                        {
                            "id": r.id,
                            "score": clamped_score,
                            "embedding": self._to_embedding(r.vector),
                            "payload": r.payload,
                        }
                    )
                )
            else:
                logger.warning(
                    f"Point {r.id} has no vector in search results (with_vectors={search_options.with_vectors if search_options else 'None'})"
                )

        logger.debug(f"Search returned {len(search_results)} results.")

        return search_results


_clip_store: QdrantVectorStore | None = None
_dino_store: QdrantVectorStore | None = None
_face_store: QdrantVectorStore | None = None


def get_clip_store(url: str, collection_name: str, vector_size: int = 512) -> QdrantVectorStore:
    """Get or create the global CLIP QdrantVectorStore singleton.

    Args:
        url: Qdrant service URL
        collection_name: Qdrant collection name
        vector_size: Embedding dimension (default 512)

    Returns:
        QdrantVectorStore singleton instance for CLIP
    """
    global _clip_store

    if _clip_store is not None:
        if _clip_store.url != url or _clip_store.collection_name != collection_name:
            raise RuntimeError(
                "ClipStore already initialized with different parameters: "
                + f"existing(url={_clip_store.url}, col={_clip_store.collection_name}), "
                + f"requested(url={url}, col={collection_name})"
            )
        return _clip_store

    _clip_store = QdrantVectorStore(
        collection_name=collection_name,
        url=url,
        vector_size=vector_size,  # Configurable
    )
    logger.info(
        f"Initialized ClipStore: url={url}, collection={collection_name}, size={vector_size}"
    )

    return _clip_store


def get_dino_store(url: str, collection_name: str, vector_size: int = 384) -> QdrantVectorStore:
    """Get or create the global DINO QdrantVectorStore singleton.

    Args:
        url: Qdrant service URL
        collection_name: Qdrant collection name
        vector_size: Embedding dimension (default 384)

    Returns:
        QdrantVectorStore singleton instance for DINOv2
    """
    global _dino_store

    if _dino_store is not None:
        if _dino_store.url != url or _dino_store.collection_name != collection_name:
            raise RuntimeError(
                "DinoStore already initialized with different parameters: "
                + f"existing(url={_dino_store.url}, col={_dino_store.collection_name}), "
                + f"requested(url={url}, col={collection_name})"
            )
        return _dino_store

    _dino_store = QdrantVectorStore(
        collection_name=collection_name,
        url=url,
        vector_size=vector_size,  # Configurable
    )
    logger.info(
        f"Initialized DinoStore: url={url}, collection={collection_name}, size={vector_size}"
    )

    return _dino_store


def get_face_store(
    url: str,
    collection_name: str,
    vector_size: int,
) -> QdrantVectorStore:
    """Get or create the global face store singleton (separate Qdrant collection).

    Args:
        url: Qdrant service URL
        collection_name: Qdrant collection name
        vector_size: Face embedding vector dimension

    Returns:
        QdrantVectorStore singleton instance for face embeddings
    """
    global _face_store

    if _face_store is not None:
        # Check for parameter mismatch (including vector_size if applicable to underlying store)
        if (
            _face_store.url != url
            or _face_store.collection_name != collection_name
            or _face_store.vector_size != vector_size
        ):
            raise RuntimeError(
                "FaceStore already initialized with different parameters: "
                + f"existing(url={_face_store.url}, col={_face_store.collection_name}, size={_face_store.vector_size}), "
                + f"requested(url={url}, col={collection_name}, size={vector_size})"
            )
        return _face_store

    _face_store = QdrantVectorStore(
        collection_name=collection_name,
        url=url,
        vector_size=vector_size,
        distance=Distance.COSINE,  # For face similarity
    )
    logger.info(
        f"Initialized Face Store: url={url}, collection={collection_name}, size={vector_size}"
    )

    return _face_store


def get_clip_store_dep(config: StoreConfig = Depends(StoreConfig.get_config)) -> QdrantVectorStore:
    """Dependency to get CLIP vector store."""
    return get_clip_store(
        url=config.qdrant_url,
        collection_name=config.qdrant_collection,
    )


def get_dino_store_dep(config: StoreConfig = Depends(StoreConfig.get_config)) -> QdrantVectorStore:
    """Dependency to get DINO vector store."""
    return get_dino_store(
        url=config.qdrant_url,
        collection_name=config.dino_collection,
    )


def get_face_store_dep(config: StoreConfig = Depends(StoreConfig.get_config)) -> QdrantVectorStore:
    """Dependency to get Face vector store."""
    return get_face_store(
        url=config.qdrant_url,
        collection_name=config.face_collection,
        vector_size=FACE_VECTOR_SIZE,
    )
