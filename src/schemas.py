from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class BodyCreateEntity(BaseModel):
    label: Optional[str] = Field(None, title="Label")
    description: Optional[str] = Field(None, title="Description")
    parent_id: Optional[int] = Field(None, title="Parent Id")
    is_collection: bool = Field(..., title="Is Collection")
    # image is part of the multipart body – handled separately


class BodyUpdateEntity(BaseModel):
    label: Optional[str] = Field(None, title="Label")
    description: Optional[str] = Field(None, title="Description")
    parent_id: Optional[int] = Field(None, title="Parent Id")
    is_collection: bool = Field(..., title="Is Collection")
    # image is part of the multipart body – handled separately


class BodyPatchEntity(BaseModel):
    label: Optional[str] = Field(None, title="Label")
    description: Optional[str] = Field(None, title="Description")
    parent_id: Optional[int] = Field(None, title="Parent Id")
    is_deleted: Optional[bool] = Field(None, title="Is Deleted")


class Item(BaseModel):
    id: Optional[int] = Field(None, title="Id", json_schema_extra={"read_only": True})
    is_collection: Optional[bool] = Field(None, title="Is Collection")
    label: Optional[str] = Field(None, title="Label")
    description: Optional[str] = Field(None, title="Description")
    parent_id: Optional[int] = Field(None, title="Parent Id")
    added_date: Optional[int] = Field(None, title="Added Date", json_schema_extra={"read_only": True})
    updated_date: Optional[int] = Field(None, title="Updated Date", json_schema_extra={"read_only": True})
    is_deleted: Optional[bool] = Field(None, title="Is Deleted")
    create_date: Optional[int] = Field(None, title="Create Date", json_schema_extra={"read_only": True})
    added_by: Optional[str] = Field(None, title="Added By", json_schema_extra={"read_only": True})
    updated_by: Optional[str] = Field(None, title="Updated By", json_schema_extra={"read_only": True})
    file_size: Optional[int] = Field(None, title="File Size", json_schema_extra={"read_only": True})
    height: Optional[int] = Field(None, title="Height", json_schema_extra={"read_only": True})
    width: Optional[int] = Field(None, title="Width", json_schema_extra={"read_only": True})
    duration: Optional[float] = Field(None, title="Duration", json_schema_extra={"read_only": True})
    mime_type: Optional[str] = Field(None, title="Mime Type", json_schema_extra={"read_only": True})
    type: Optional[str] = Field(None, title="Type", json_schema_extra={"read_only": True})
    extension: Optional[str] = Field(None, title="Extension", json_schema_extra={"read_only": True})
    md5: Optional[str] = Field(None, title="Md5", json_schema_extra={"read_only": True})
    file_path: Optional[str] = Field(None, title="File Path", json_schema_extra={"read_only": True})


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
    updated_at: Optional[int] = Field(None, description="Last update timestamp (milliseconds)")
    updated_by: Optional[str] = Field(None, description="User ID who last updated the config")


class UpdateReadAuthConfig(BaseModel):
    """Request schema for updating read auth configuration."""
    enabled: bool = Field(..., description="Whether to enable read authentication")

