from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class Entity(Base):
    """SQLAlchemy model for media entities."""
    
    __tablename__ = "entities"
    __versioned__ = {}  # Enable SQLAlchemy-Continuum versioning
    
    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Core fields
    is_collection: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Timestamps
    added_date: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    updated_date: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    create_date: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    # User identity tracking
    added_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # File metadata
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    extension: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    md5: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True, nullable=True)
    
    # File storage
    file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Soft delete flag
    is_deleted: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, nullable=True)
    
    def __repr__(self) -> str:
        return f"<Entity(id={self.id}, label={self.label})>"


class ServiceConfig(Base):
    """SQLAlchemy model for service configuration."""
    
    __tablename__ = "service_config"
    
    # Primary key
    key: Mapped[str] = mapped_column(String, primary_key=True)
    
    # Configuration value (stored as string, parsed as needed)
    value: Mapped[str] = mapped_column(String, nullable=False)
    
    # Metadata
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    def __repr__(self) -> str:
        return f"<ServiceConfig(key={self.key}, value={self.value})>"
