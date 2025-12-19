from __future__ import annotations

from typing import Optional

# Job Management Schemas (from compute service)
# Import base Job schema from library for consistency
from cl_ml_tools import Job as BaseJob
from pydantic import BaseModel, Field


class BodyCreateEntity(BaseModel):
    label: str | None = Field(None, title="Label")
    description: str | None = Field(None, title="Description")
    parent_id: int | None = Field(None, title="Parent Id")
    is_collection: bool = Field(..., title="Is Collection")
    # image is part of the multipart body – handled separately


class BodyUpdateEntity(BaseModel):
    label: str | None = Field(None, title="Label")
    description: str | None = Field(None, title="Description")
    parent_id: int | None = Field(None, title="Parent Id")
    is_collection: bool = Field(..., title="Is Collection")
    # image is part of the multipart body – handled separately


class BodyPatchEntity(BaseModel):
    label: str | None = Field(None, title="Label")
    description: str | None = Field(None, title="Description")
    parent_id: int | None = Field(None, title="Parent Id")
    is_deleted: bool | None = Field(None, title="Is Deleted")


class Item(BaseModel):
    id: int | None = Field(None, title="Id", json_schema_extra={"read_only": True})
    is_collection: bool | None = Field(None, title="Is Collection")
    label: str | None = Field(None, title="Label")
    description: str | None = Field(None, title="Description")
    parent_id: int | None = Field(None, title="Parent Id")
    added_date: int | None = Field(None, title="Added Date", json_schema_extra={"read_only": True})
    updated_date: int | None = Field(
        None, title="Updated Date", json_schema_extra={"read_only": True}
    )
    is_deleted: bool | None = Field(None, title="Is Deleted")
    create_date: int | None = Field(
        None, title="Create Date", json_schema_extra={"read_only": True}
    )
    added_by: str | None = Field(None, title="Added By", json_schema_extra={"read_only": True})
    updated_by: str | None = Field(None, title="Updated By", json_schema_extra={"read_only": True})
    file_size: int | None = Field(None, title="File Size", json_schema_extra={"read_only": True})
    height: int | None = Field(None, title="Height", json_schema_extra={"read_only": True})
    width: int | None = Field(None, title="Width", json_schema_extra={"read_only": True})
    duration: float | None = Field(None, title="Duration", json_schema_extra={"read_only": True})
    mime_type: str | None = Field(None, title="Mime Type", json_schema_extra={"read_only": True})
    type: str | None = Field(None, title="Type", json_schema_extra={"read_only": True})
    extension: str | None = Field(None, title="Extension", json_schema_extra={"read_only": True})
    md5: str | None = Field(None, title="Md5", json_schema_extra={"read_only": True})
    file_path: str | None = Field(None, title="File Path", json_schema_extra={"read_only": True})


class PaginationMetadata(BaseModel):
    """Pagination metadata for paginated responses."""

    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Number of items per page")
    total_items: int = Field(..., description="Total number of items across all pages")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_prev: bool = Field(..., description="Whether there is a previous page")


class PaginatedResponse(BaseModel):
    """Paginated response wrapper for entity lists."""

    items: list[Item] = Field(..., description="List of items for the current page")
    pagination: PaginationMetadata = Field(..., description="Pagination metadata")


# Admin configuration schemas
class ConfigResponse(BaseModel):
    """Response schema for configuration."""

    read_auth_enabled: bool = Field(..., description="Whether read authentication is enabled")
    updated_at: int | None = Field(None, description="Last update timestamp (milliseconds)")
    updated_by: str | None = Field(None, description="User ID who last updated the config")


class UpdateReadAuthConfig(BaseModel):
    """Request schema for updating read auth configuration."""

    enabled: bool = Field(..., description="Whether to enable read authentication")


class JobResponse(BaseJob):
    """Response schema for job information.

    Extends the library's Job schema with service-specific fields
    for timestamps and priority.
    """

    priority: int = Field(5, description="Job priority (0-10)")
    created_at: int = Field(..., description="Job creation timestamp (milliseconds)")
    updated_at: int | None = Field(None, description="Job last update timestamp (milliseconds)")
    started_at: int | None = Field(None, description="Job start timestamp (milliseconds)")
    completed_at: int | None = Field(None, description="Job completion timestamp (milliseconds)")


class StorageInfo(BaseModel):
    """Response schema for storage information."""

    total_size: int = Field(..., description="Total storage usage in bytes")
    job_count: int = Field(..., description="Number of jobs stored")


class CleanupResult(BaseModel):
    """Response schema for cleanup operation results."""

    deleted_count: int = Field(..., description="Number of jobs deleted")
    freed_space: int = Field(..., description="Space freed in bytes")
