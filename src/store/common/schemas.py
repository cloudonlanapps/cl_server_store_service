from __future__ import annotations

from typing import ClassVar
from pydantic import BaseModel, ConfigDict, Field


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
    is_indirectly_deleted: bool | None = Field(
        None,
        title="Is Indirectly Deleted",
        description="True if any ancestor in the parent chain is soft-deleted",
    )
    intelligence_status: str | None = Field(
        None,
        title="Intelligence Status",
        description="Status of image intelligence processing (queued, processing, completed, failed)",
    )


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

    guest_mode: bool = Field(
        ..., description="Whether guest mode is enabled (true = no authentication required)"
    )
    updated_at: int | None = Field(None, description="Last update timestamp (milliseconds)")
    updated_by: str | None = Field(None, description="User ID who last updated the config")


class UpdateReadAuthConfig(BaseModel):
    """Request schema for updating read authentication configuration."""

    enabled: bool = Field(..., description="Whether to enable read authentication")


class VersionInfo(BaseModel):
    """Information about an entity version."""

    version: int = Field(..., description="Version number (1-indexed)")
    transaction_id: int | None = Field(None, description="Transaction ID of the version")
    updated_date: int | None = Field(None, description="Last update timestamp (milliseconds)")

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class MInsightProcessStatus(BaseModel):
    """Status information for a single MInsight process."""

    status: str = Field(..., description="Process status (unknown, running, idle)")
    last_update: int = Field(..., description="Last update timestamp (milliseconds)")
    port: int = Field(..., description="Process port")
    # MQTT heartbeat can include more fields
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow", from_attributes=True)


class MInsightStatusResponse(BaseModel):
    """Response schema for MInsight process status."""

    # Using a list instead of dict for better API compatibility and typing
    processes: list[MInsightProcessStatus] = Field(..., description="List of monitored processes")
