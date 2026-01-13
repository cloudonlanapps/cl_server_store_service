from typing import cast, override

import numpy as np
from loguru import logger
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict
from qdrant_client import QdrantClient
from qdrant_client.http.models import HnswConfigDiff, PointStruct
from qdrant_client.http.models.models import Payload
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

from .store_interface import StoreInterface


class StoreItem(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: StrictInt
    embedding: NDArray[np.float32]
    payload: Payload | None
    pass


class SearchPreferences(BaseModel):
    with_payload: bool = True
    with_vectors: bool = False
    score_threshold: float = 0.85
    pass


class SearchResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: int
    embedding: NDArray[np.float32]
    score: float
    payload: Payload | None
    pass


class QdrantImageStore(StoreInterface[StoreItem, SearchPreferences, SearchResult]):
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

        logger.debug(f"Upserted: {item.id} ")
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

        search_results: list[SearchResult] = [
            SearchResult.model_validate(
                {
                    "id": r.id,
                    "score": r.score,
                    "embedding": r.vector,
                    "payload": r.payload,
                }
            )
            for r in results
        ]

        logger.debug(f"Search returned {len(search_results)} results.")

        return search_results
