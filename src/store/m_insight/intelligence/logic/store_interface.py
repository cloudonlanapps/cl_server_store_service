from abc import ABC, abstractmethod
from typing import TypeVar

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel

SearchOptionsT = TypeVar("SearchOptionsT", bound=BaseModel)
StoreItemT = TypeVar("StoreItemT", bound=BaseModel)
SearchPreferencesT = TypeVar("SearchPreferencesT", bound=BaseModel)


class StoreInterface[StoreItemT, SearchOptionsT, SearchResultT](ABC):
    """
    Abstract base class for a generic vector store interface.

    This class defines a standard interface for interacting with a vector store,
    allowing for different underlying implementations (e.g., Qdrant, Milvus, FAISS).
    Subclasses must implement methods for adding, retrieving, deleting, and searching vectors.
    """

    @abstractmethod
    def add_vector(self, item: StoreItemT) -> int:
        """
        Adds a single vector to the store with a given ID and optional payload.
        """
        pass

    @abstractmethod
    def get_vector(self, id: int) -> StoreItemT | None:
        """
        Retrieves a vector by its ID.
        """
        pass

    @abstractmethod
    def delete_vector(self, id: int):
        """
        Deletes a vector by its ID.
        """
        pass

    @abstractmethod
    def search(
        self,
        query_vector: NDArray[np.float32],
        limit: int = 5,
        search_options: SearchOptionsT | None = None,
    ) -> list[SearchResultT]:
        """
        Searches for similar vectors in the store.
        """
        pass
