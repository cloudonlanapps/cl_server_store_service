"""Type stubs for sqlalchemy_continuum."""

from typing import Any, Protocol, TypeVar

from sqlalchemy.orm import Query

_T = TypeVar("_T")

class VersionedModel(Protocol):
    """Protocol for models with versioning enabled."""

    transaction_id: int | None
    operation_type: int | None
    end_transaction_id: int | None

class VersionsRelationship(Protocol[_T]):
    """Protocol for the versions relationship added by continuum."""

    def all(self) -> list[_T]: ...
    def filter(self, *args: Any, **kwargs: Any) -> Query[_T]: ...  # pyright: ignore[reportAny, reportExplicitAny]
    def count(self) -> int: ...

def make_versioned(options: dict[str, Any] | None = None, user_cls: Any | None = None) -> None:  # pyright: ignore[reportExplicitAny]
    """Configure SQLAlchemy-Continuum versioning."""
    ...

def versioning_manager(*args: Any, **kwargs: Any) -> Any:  # pyright: ignore[reportAny, reportExplicitAny]
    """Get the versioning manager instance."""
    ...
