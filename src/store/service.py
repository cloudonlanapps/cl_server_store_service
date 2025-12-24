from __future__ import annotations

import logging
from datetime import UTC, datetime

from cl_server_shared import Config
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .entity_storage import EntityStorageService
from .media_metadata import MediaMetadataExtractor
from .models import Entity
from .schemas import BodyCreateEntity, BodyPatchEntity, BodyUpdateEntity, Item


class DuplicateFileError(Exception):
    """Raised when attempting to upload a file with duplicate MD5."""

    pass


class EntityService:
    """Service layer for entity operations."""

    def __init__(self, db: Session):
        """Initialize the entity service.

        Args:
            db: SQLAlchemy database session
        """
        self.db: Session = db
        # Use MEDIA_STORAGE_DIR for entity files (organized by date)
        self.file_storage: EntityStorageService = EntityStorageService(
            base_dir=Config.MEDIA_STORAGE_DIR
        )
        # Initialize metadata extractor
        self.metadata_extractor: MediaMetadataExtractor = MediaMetadataExtractor()

    @staticmethod
    def _now_timestamp() -> int:
        """Return current UTC timestamp in milliseconds."""
        return int(datetime.now(UTC).timestamp() * 1000)

    def _check_duplicate_md5(self, md5: str, exclude_entity_id: int | None = None) -> Entity | None:
        """
        Check if an entity with the given MD5 already exists.

        Args:
            md5: MD5 hash to check
            exclude_entity_id: Optional entity ID to exclude from check (for updates)

        Returns:
            Entity if duplicate found, None otherwise
        """
        query = self.db.query(Entity).filter(Entity.md5 == md5)

        if exclude_entity_id is not None:
            query = query.filter(Entity.id != exclude_entity_id)

        return query.first()

    @staticmethod
    def _entity_to_item(entity: Entity) -> Item:
        """
        Convert SQLAlchemy Entity to Pydantic Item schema.

        Args:
            entity: SQLAlchemy Entity instance (or version object from SQLAlchemy-Continuum)

        Returns:
            Pydantic Item instance
        """
        return Item(
            id=entity.id,
            is_collection=entity.is_collection,
            label=entity.label,
            description=entity.description,
            parent_id=entity.parent_id,
            added_date=entity.added_date,
            updated_date=entity.updated_date,
            create_date=entity.create_date,
            added_by=entity.added_by,
            updated_by=entity.updated_by,
            file_size=entity.file_size,
            height=entity.height,
            width=entity.width,
            duration=entity.duration,
            mime_type=entity.mime_type,
            type=entity.type,
            extension=entity.extension,
            md5=entity.md5,
            file_path=entity.file_path,
            is_deleted=entity.is_deleted,
        )

    def get_entities(
        self,
        page: int = 1,
        page_size: int = 20,
        version: int | None = None,
        filter_param: str | None = None,  # pyright: ignore[reportUnusedParameter]
        search_query: str | None = None,  # pyright: ignore[reportUnusedParameter]
    ) -> tuple[list[Item], int]:
        """
        Retrieve all entities with optional pagination and versioning.

        Args:
            page: Page number (1-indexed)
            page_size: Number of items per page
            version: Optional version number to retrieve for all entities
            filter_param: Optional filter string (not implemented yet)
            search_query: Optional search query (not implemented yet)

        Returns:
            Tuple of (items, total_count)
        """
        query = self.db.query(Entity)

        # TODO: Implement filtering and search logic
        # For now, return all entities

        # Get total count before pagination
        total_count = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.order_by(Entity.id.asc()).offset(offset).limit(page_size)

        entities = query.all()

        # If version is specified, get that version of each entity
        if version is not None:
            items: list[Item] = []
            for entity in entities:
                versioned_item = self.get_entity_version(entity.id, version)
                if versioned_item:  # Only include if version exists
                    items.append(versioned_item)
        else:
            items = [self._entity_to_item(entity) for entity in entities]

        return items, total_count

    def get_entity_by_id(self, entity_id: int, version: int | None = None) -> Item | None:
        """
        Retrieve a single entity by ID, optionally at a specific version.

        Args:
            entity_id: Entity ID
            version: Optional version number to retrieve (None = latest)

        Returns:
            Item instance or None if not found
        """
        if version is not None:
            return self.get_entity_version(entity_id, version)

        entity = self.db.query(Entity).filter(Entity.id == entity_id).first()
        if entity:
            return self._entity_to_item(entity)
        return None

    def get_entity_version(self, entity_id: int, version: int) -> Item | None:
        """
        Retrieve a specific version of an entity.

        Args:
            entity_id: Entity ID
            version: Version number to retrieve (1-indexed)

        Returns:
            Item instance for the specified version or None if not found
        """
        # First check if the entity exists
        entity = self.db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            return None

        # Get the specific version
        # SQLAlchemy-Continuum creates a versions relationship on the model
        if hasattr(entity, "versions"):
            versions_list = entity.versions.all()
            # Versions are 1-indexed for the API
            if 1 <= version <= len(versions_list):
                version_entity = versions_list[version - 1]  # pyright: ignore[reportAny]
                return self._entity_to_item(version_entity)  # pyright: ignore[reportAny]

        return None

    def get_entity_versions(self, entity_id: int) -> list[dict[str, int | None]]:
        """
        Get all versions of an entity with metadata.

        Args:
            entity_id: Entity ID

        Returns:
            List of version metadata dictionaries
        """
        entity = self.db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            return []

        if not hasattr(entity, "versions"):
            return []

        versions_list = entity.versions.all()
        result: list[dict[str, int | None]] = []
        for idx, version in enumerate(versions_list, start=1):  # pyright: ignore[reportAny]
            version_info: dict[str, int | None] = {
                "version": idx,
                "transaction_id": (
                    version.transaction_id if hasattr(version, "transaction_id") else None  # pyright: ignore[reportAny]
                ),
                "updated_date": (
                    version.updated_date if hasattr(version, "updated_date") else None  # pyright: ignore[reportAny]
                ),
            }
            result.append(version_info)

        return result

    def create_entity(
        self,
        body: BodyCreateEntity,
        image: bytes | None = None,
        filename: str = "file",
        user_id: str | None = None,
    ) -> Item:
        """
        Create a new entity.

        Args:
            body: Entity creation data
            image: Optional image file bytes
            filename: Original filename
            user_id: Optional user identifier from JWT (None in demo mode)

        Returns:
            Created Item instance

        Raises:
            DuplicateFileError: If file with same MD5 already exists
        """
        now = self._now_timestamp()
        file_meta = None
        file_path = None

        # Validation: image is required if is_collection is False
        if not body.is_collection and not image:
            raise ValueError("Image is required when is_collection is False")

        # Validation: image should not be present if is_collection is True
        if body.is_collection and image:
            raise ValueError("Image should not be provided when is_collection is True")

        # Extract metadata and save file if provided
        if image:
            # Extract metadata using MediaMetadataExtractor
            file_meta = self.metadata_extractor.extract_metadata(image, filename)

            # Check for duplicate MD5
            duplicate = self._check_duplicate_md5(file_meta.md5)
            if duplicate:
                # Return the existing item instead of raising an error
                return self._entity_to_item(duplicate)

            # Save file to storage (convert Pydantic model to dict for storage)
            logging.error(f"{filename} is sent for saving with metadata {file_meta.model_dump()}")
            file_path = self.file_storage.save_file(image, file_meta.model_dump(), filename)
            logging.error(f"filepath received: {file_path}")
            logging.error(self.file_storage.base_dir)

        # Extract metadata values from Pydantic model (or None for collections)
        if file_meta:
            file_size = file_meta.file_size
            height = file_meta.height
            width = file_meta.width
            duration = file_meta.duration
            mime_type = file_meta.mime_type
            type_str = file_meta.type
            extension = file_meta.extension
            md5 = file_meta.md5
        else:
            # No file metadata for collections
            file_size = None
            height = None
            width = None
            duration = None
            mime_type = None
            type_str = None
            extension = None
            md5 = None

        entity = Entity(
            is_collection=body.is_collection,
            label=body.label,
            description=body.description,
            parent_id=body.parent_id,
            added_date=now,
            updated_date=now,
            create_date=now,
            file_size=file_size,
            height=height,
            width=width,
            duration=duration,
            mime_type=mime_type,
            type=type_str,
            extension=extension,
            md5=md5,
            file_path=file_path,
            is_deleted=False,
            added_by=user_id,
            updated_by=user_id,
        )

        try:
            self.db.add(entity)
            self.db.commit()
            self.db.refresh(entity)
        except IntegrityError as _:
            self.db.rollback()
            # Clean up file if database insert failed
            if file_path:
                _ = self.file_storage.delete_file(file_path)
            raise DuplicateFileError(
                f"Duplicate MD5 detected: {file_meta.md5 if file_meta else 'unknown'}"
            )

        return self._entity_to_item(entity)

    def update_entity(
        self,
        entity_id: int,
        body: BodyUpdateEntity,
        image: bytes | None,
        filename: str = "file",
        user_id: str | None = None,
    ) -> Item | None:
        """
        Fully update an existing entity (PUT) - file upload is optional for non-collections.

        Args:
            entity_id: Entity ID
            body: Entity update data
            image: Image file bytes (optional - if None, only metadata is updated)
            filename: Original filename
            user_id: Optional user identifier from JWT (None in demo mode)

        Returns:
            Updated Item instance or None if not found

        Raises:
            DuplicateFileError: If file with same MD5 already exists
        """
        entity = self.db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            return None

        # Validation: is_collection should not be changed
        # The body.is_collection from the request should match the existing entity.is_collection
        if body.is_collection != entity.is_collection:
            raise ValueError(
                f"Cannot change is_collection from {entity.is_collection} to {body.is_collection}. "
                + "is_collection is immutable after entity creation."
            )

        # Validation: image should not be present if is_collection is True
        if entity.is_collection and image:
            raise ValueError("Image should not be provided when is_collection is True")

        # Note: image is optional if is_collection is False (for PUT operations)
        # This allows updating metadata without changing the file
        file_path = None
        file_meta = None
        if image:
            # Extract metadata from new file
            file_meta = self.metadata_extractor.extract_metadata(image, filename)

            # Check for duplicate MD5 (excluding current entity)
            duplicate = self._check_duplicate_md5(file_meta.md5, exclude_entity_id=entity_id)
            if duplicate:
                # Return the existing item instead of raising an error
                return self._entity_to_item(duplicate)

            # Delete old file if exists
            old_file_path = entity.file_path
            if old_file_path:
                _ = self.file_storage.delete_file(old_file_path)

            # Save new file (convert Pydantic model to dict for storage)
            file_path = self.file_storage.save_file(image, file_meta.model_dump(), filename)

            # Update file metadata from Pydantic model
            entity.file_size = file_meta.file_size
            entity.height = file_meta.height
            entity.width = file_meta.width
            entity.duration = file_meta.duration
            entity.mime_type = file_meta.mime_type
            entity.type = file_meta.type
            entity.extension = file_meta.extension
            entity.md5 = file_meta.md5
            entity.file_path = file_path

        # Update entity with new metadata and client-provided fields
        now = self._now_timestamp()

        entity.label = body.label
        entity.description = body.description
        entity.parent_id = body.parent_id
        entity.updated_date = now
        entity.updated_by = user_id

        try:
            self.db.commit()
            self.db.refresh(entity)
        except IntegrityError:
            self.db.rollback()
            # Clean up new file if database update failed
            if file_path:
                _ = self.file_storage.delete_file(file_path)
            raise DuplicateFileError(
                f"Duplicate MD5 detected: {file_meta.md5 if file_meta else ''}"
            )

        return self._entity_to_item(entity)

    def patch_entity(
        self, entity_id: int, body: BodyPatchEntity, user_id: str | None = None
    ) -> Item | None:
        """
        Partially update an existing entity (PATCH).

        Args:
            entity_id: Entity ID
            body: Entity patch data (only provided fields will be updated)
            user_id: Optional user identifier from JWT (None in demo mode)

        Returns:
            Updated Item instance or None if not found
        """
        entity = self.db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            return None

        # Update only provided fields (get values from Pydantic model to preserve types)
        for field_name in body.model_dump(exclude_unset=True):
            setattr(entity, field_name, getattr(body, field_name))

        entity.updated_date = self._now_timestamp()
        entity.updated_by = user_id

        self.db.commit()
        self.db.refresh(entity)

        return self._entity_to_item(entity)

    def delete_entity(self, entity_id: int) -> Item | None:
        """
        Soft delete an entity (set is_deleted=True).

        Args:
            entity_id: Entity ID

        Returns:
            Deleted Item instance or None if not found
        """
        entity = self.db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            return None

        # Hard delete: remove file and database record
        if entity.file_path:
            _ = self.file_storage.delete_file(entity.file_path)

        self.db.delete(entity)
        _ = self.db.commit()

        return self._entity_to_item(entity)

    def delete_all_entities(self) -> None:
        """Delete all entities from the database."""
        _ = self.db.query(Entity).delete()
        _ = self.db.commit()
