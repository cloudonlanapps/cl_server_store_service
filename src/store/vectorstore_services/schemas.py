from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict
from qdrant_client.http.models.models import Payload
from qdrant_client.models import StrictInt

class StoreItem(BaseModel):
    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)  # pyright: ignore[reportIncompatibleVariableOverride]
    id: StrictInt
    embedding: NDArray[np.float32]
    payload: Payload | None


class SearchPreferences(BaseModel):
    with_payload: bool = True
    with_vectors: bool = True
    score_threshold: float = 0.85


class SearchResult(BaseModel):
    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)  # pyright: ignore[reportIncompatibleVariableOverride]
    id: int
    embedding: NDArray[np.float32]
    score: float
    payload: Payload | None
