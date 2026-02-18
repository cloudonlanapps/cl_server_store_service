from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from loguru import logger
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


from store.db_service import EntitySchema
from store.db_service.db_internals import Entity
from store.db_service.schemas import VersionInfo

from ..common.storage import StorageService
from .config import StoreConfig
from .media_metadata import MediaMetadataExtractor
from .media_thumbnail import ThumbnailGenerator

if TYPE_CHECKING:
    from .face_service import FaceService
    from store.vectorstore_services.vector_stores import QdrantVectorStore
    from ..broadcast_service.broadcaster import MInsightBroadcaster


class DuplicateFileError(Exception):
    """Raised when attempting to upload a file with duplicate MD5."""

    pass


class EntityNotSoftDeletedError(Exception):
    """Raised when attempting to hard delete an entity that is not soft-deleted."""

    pass


class EntityService:
    """Service layer for entity operations."""

    def __init__(
        self,
        db: Session,
        config: StoreConfig,
        face_service: FaceService | None = None,
        clip_store: QdrantVectorStore | None = None,
        dino_store: QdrantVectorStore | None = None,
        broadcaster: MInsightBroadcaster | None = None,
    ):
        """Initialize the entity service.

        Args:
            db: SQLAlchemy database session
            config: Store configuration
            face_service: Optional face service for deletion operations
            clip_store: Optional CLIP vector store for deletion operations
            dino_store: Optional DINO vector store for deletion operations
            broadcaster: Optional MQTT broadcaster for clearing retained messages
        """
        self.db: Session = db
        self.config: StoreConfig = config
        self.file_storage: StorageService = StorageService(base_dir=str(config.media_storage_dir))
        # Initialize metadata extractor
        self.metadata_extractor: MediaMetadataExtractor = MediaMetadataExtractor()
        # Optional dependencies for deletion operations
        self.face_service: FaceService | None = face_service
        self.clip_store: QdrantVectorStore | None = clip_store
        self.dino_store: QdrantVectorStore | None = dino_store
        self.broadcaster: MInsightBroadcaster | None = broadcaster

    def get_media_path(self, entity: EntitySchema) -> str | None:
        """Get absolute path to the media file."""
        if not entity.file_path:
            return None
        return str(self.file_storage.get_absolute_path(entity.file_path))

    def get_stream_path(self, entity: EntitySchema, filename: str = "adaptive.m3u8") -> str | None:
        """Get absolute path to a stream file."""
        if not entity.mime_type:
            return None
            
        # Structure matches media_repo: streams/mime/type/media_{id}/filename
        # e.g. streams/video/mp4/media_123/adaptive.m3u8
        # We assume stream_storage_dir is set in config
        stream_dir = self.config.stream_storage_dir
        if not stream_dir:
            return None
            
        return str(stream_dir / entity.mime_type / f"media_{entity.id}" / filename)

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
            Entity if duplicate found, None otherwise (excludes soft-deleted entities)
        """
        query = self.db.query(Entity).filter(Entity.md5 == md5).filter(Entity.is_deleted == False)  # noqa: E712

        if exclude_entity_id is not None:
            query = query.filter(Entity.id != exclude_entity_id)

        return query.first()

    def _validate_parent_id(
        self,
        parent_id: int | None,
        _is_collection: bool,
        entity_id: int | None = None,
    ) -> None:
        """
        Validate parent_id against business rules.

        Args:
            parent_id: Parent entity ID to validate
            is_collection: Whether the entity being validated is a collection
            entity_id: ID of entity being updated (None for create operations)

        Raises:
            ValueError: If validation fails with descriptive error message
        """
        # Rule: Non-collections must have a parent
        pass

        # If parent_id is None and allowed (collections), no further validation needed
        if parent_id is None:
            return

        # Rule: Parent must exist
        parent = self.db.query(Entity).filter(Entity.id == parent_id).first()
        if not parent:
            raise ValueError(f"Cannot set parent_id to {parent_id}: parent entity does not exist")

        # Rule: Parent must be a collection
        if not parent.is_collection:
            raise ValueError(
                f"Cannot set parent_id to {parent_id}: parent entity must be a collection. "
                + f"Entity {parent_id} is not a collection."
            )

        # Rule: Parent must not be soft-deleted
        if parent.is_deleted:
            raise ValueError(f"Cannot set parent_id to {parent_id}: parent entity is deleted")

        # Rule: Prevent circular hierarchies (only for updates)
        if entity_id is not None:
            current_parent = parent_id
            visited = {entity_id}
            while current_parent is not None:
                if current_parent in visited:
                    raise ValueError(
                        f"Circular hierarchy detected: entity {parent_id} is already "
                        + f"a descendant of {entity_id}"
                    )
                visited.add(current_parent)
                parent_entity = self.db.query(Entity).filter(Entity.id == current_parent).first()
                current_parent = parent_entity.parent_id if parent_entity else None

        # Rule: Max hierarchy depth check (max 10 levels)
        depth = 1  # Starting at depth 1 (the parent)
        current_check = parent_id
        while current_check is not None:
            parent_ent = self.db.query(Entity).filter(Entity.id == current_check).first()
            if not parent_ent:
                break
            current_check = parent_ent.parent_id
            depth += 1
            if depth > 10:
                raise ValueError(
                    "Maximum hierarchy depth exceeded. Max allowed depth is 10 levels."
                )

    def _check_ancestor_deleted(self, entity: Entity) -> bool:
        """
        Check if any ancestor in the parent chain is soft-deleted.

        Args:
            entity: Entity to check

        Returns:
            True if any ancestor is deleted, False otherwise
        """
        current_parent_id = entity.parent_id
        visited = {entity.id}  # Prevent infinite loops in corrupted data

        while current_parent_id is not None:
            # Prevent infinite loops
            if current_parent_id in visited:
                break
            visited.add(current_parent_id)

            # Check parent
            parent = self.db.query(Entity).filter(Entity.id == current_parent_id).first()
            if not parent:
                # Parent doesn't exist (orphaned entity)
                break

            # Check if parent is deleted
            if parent.is_deleted:
                return True

            # Move up the chain
            current_parent_id = parent.parent_id

        return False

    def _entity_to_item(self, entity: Entity, children_count: int = 0) -> EntitySchema:
        """
        Convert SQLAlchemy Entity to Pydantic Item schema.

        Args:
            entity: SQLAlchemy Entity instance (or version object from SQLAlchemy-Continuum)
            children_count: Number of children (only relevant for collections)

        Returns:
            Pydantic EntitySchema instance
        """



        return EntitySchema(
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
            is_indirectly_deleted=self._check_ancestor_deleted(entity),
            children_count=children_count,
        )


    def get_entities(
        self,
        page: int = 1,
        page_size: int = 20,
        version: int | None = None,
        filter_param: str | None = None,
        search_query: str | None = None,
        exclude_deleted: bool = False,
        # New filters
        md5: str | None = None,
        mime_type: str | None = None,
        type_: str | None = None,
        width: int | None = None,
        height: int | None = None,
        file_size_min: int | None = None,
        file_size_max: int | None = None,
        date_from: int | None = None,
        date_to: int | None = None,
        parent_id: int | None = None,
        is_collection: bool | None = None,
    ) -> tuple[list[EntitySchema], int]:
        """
        Retrieve all entities with optional pagination, versioning, and filtering.

        Args:
            page: Page number (1-indexed)
            page_size: Number of items per page
            version: Optional version number to retrieve for all entities
            filter_param: Optional filter string
            search_query: Optional search query
            exclude_deleted: Whether to exclude soft-deleted entities
            md5: Filter by MD5
            mime_type: Filter by MIME type
            type_: Filter by media type (image, video)
            width: Filter by exact width
            height: Filter by exact height
            file_size_min: Filter by min file size
            file_size_max: Filter by max file size
            date_from: Filter by added date from (timestamp ms)
            date_to: Filter by added date to (timestamp ms)
            parent_id: Filter by parent collection ID (0 = root-level items)
            is_collection: Filter by collection (true) vs media item (false)

        Returns:
            Tuple of (items, total_count)
        """
        query = self.db.query(Entity)

        if exclude_deleted:
            query = query.filter(Entity.is_deleted == False)  # noqa: E712

        if search_query:
            search = f"%{search_query}%"
            query = query.filter(Entity.label.ilike(search))

        # Apply specific filters
        if md5:
            query = query.filter(Entity.md5 == md5)
        
        if mime_type:
            query = query.filter(Entity.mime_type == mime_type)

        if type_:
            query = query.filter(Entity.type == type_)

        if width is not None:
            query = query.filter(Entity.width == width)

        if height is not None:
            query = query.filter(Entity.height == height)

        if file_size_min is not None:
            query = query.filter(Entity.file_size >= file_size_min)

        if file_size_max is not None:
            query = query.filter(Entity.file_size <= file_size_max)

        if date_from is not None:
            query = query.filter(Entity.added_date >= date_from)
            
        if date_to is not None:
            query = query.filter(Entity.added_date <= date_to)

        if parent_id is not None:
            if parent_id == 0:
                # Special value: root-level items (no parent)
                query = query.filter(Entity.parent_id == None)  # noqa: E711
            else:
                query = query.filter(Entity.parent_id == parent_id)

        if is_collection is not None:
            query = query.filter(Entity.is_collection == is_collection)

        # Count total before pagination
        total_items = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.order_by(Entity.added_date.desc()).offset(offset).limit(page_size)
        results = query.all()

        # Hande versioning if requested
        if version is not None:
            items_list: list[EntitySchema] = []
            for entity in results:
                versioned_item = self.get_entity_version(entity.id, version)
                if versioned_item:  # Only include if version exists
                    items_list.append(versioned_item)
            return items_list, total_items

        # Get children counts for the results
        entity_ids = [e.id for e in results]
        counts = {}
        if entity_ids:
            count_query = self.db.query(
                Entity.parent_id, func.count(Entity.id)
            ).filter(
                Entity.parent_id.in_(entity_ids)
            )
            if exclude_deleted:
                count_query = count_query.filter(Entity.is_deleted == False)
            
            # Execute and convert to dict {parent_id: count}
            counts = dict(count_query.group_by(Entity.parent_id).all())

        items: list[EntitySchema] = []
        for entity in results:
            items.append(self._entity_to_item(entity, children_count=counts.get(entity.id, 0)))

        return items, total_items


    def lookup_entity(
        self,
        md5: str | None = None,
        label: str | None = None,
    ) -> EntitySchema | None:
        """Lookup a single entity by MD5 (media) or label (collection).

        Args:
            md5: MD5 to lookup (implies is_collection=false)
            label: Label to lookup (implies is_collection=true)

        Returns:
            EntitySchema if found, None otherwise

        Raises:
            HTTPException(409) if multiple matches found (data integrity issue)
        """
        query = self.db.query(Entity)
        query = query.filter(Entity.is_deleted == False)  # noqa: E712

        if md5:
            query = query.filter(Entity.md5 == md5)
            query = query.filter(Entity.is_collection == False)  # noqa: E712
        elif label:
            query = query.filter(Entity.label == label)
            query = query.filter(Entity.is_collection == True)  # noqa: E712

        results = query.all()

        if not results:
            return None

        if len(results) > 1:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=409,
                detail=f"Multiple matches found ({len(results)} entities). Data integrity issue.",
            )

        return self._entity_to_item(results[0])

    def get_entity_by_id(self, entity_id: int, version: int | None = None) -> EntitySchema | None:
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

        result = (
            self.db.query(Entity)
            .filter(Entity.id == entity_id)
            .first()
        )

        if result:
            children_count = self.db.query(Entity).filter(Entity.parent_id == entity_id, Entity.is_deleted == False).count()
            return self._entity_to_item(result, children_count=children_count)
        return None


    def get_entity_version(self, entity_id: int, version: int) -> EntitySchema | None:
        """
        Retrieve a specific version of an entity.

        Args:
            entity_id: Entity ID
            version: Version number to retrieve (1-indexed)

        Returns:
            EntitySchema instance for the specified version or None if not found
        """
        # First check if the entity exists
        entity = self.db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            return None

        # Get the specific version
        # SQLAlchemy-Continuum creates a versions relationship on the model
        if hasattr(entity, "versions"):
            versions_list = cast(list[Entity], entity.versions.all())  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
            # Versions are 1-indexed for the API
            if 1 <= version <= len(versions_list):
                version_entity = versions_list[version - 1]
                return self._entity_to_item(version_entity)

        return None

    def get_entity_versions(self, entity_id: int) -> list[VersionInfo]:
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

        versions_list = entity.versions.all()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportAttributeAccessIssue]
        result: list[VersionInfo] = []
        for idx, version in enumerate(versions_list, start=1):  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
            # SQLAlchemy-Continuum version objects can be validated via model_validate
            # with from_attributes=True enabled in the schema
            # Create dictionary with required fields
            version_data = {  # pyright: ignore[reportUnknownVariableType]
                "transaction_id": version.transaction_id,  # pyright: ignore[reportUnknownMemberType]
                "updated_date": version.updated_date,  # pyright: ignore[reportUnknownMemberType]
                "version": idx,
            }
            version_info = VersionInfo.model_validate(version_data)
            result.append(version_info)

        return result

    def create_entity(
        self,
        is_collection: bool,
        label: str | None = None,
        description: str | None = None,
        parent_id: int | None = None,
        media_file: bytes | None = None,
        filename: str = "file",
        user_id: str | None = None,
    ) -> tuple[EntitySchema, bool]:
        """
        Create a new entity.

        Args:
            is_collection: Whether the entity is a collection
            label: Entity label
            description: Entity description
            parent_id: Parent entity ID
            media_file: Optional media file bytes
            filename: Original filename
            user_id: Optional user identifier from JWT (None in demo mode)

        Returns:
            Created EntitySchema instance

        Raises:
            DuplicateFileError: If file with same MD5 already exists
        """
        now = self._now_timestamp()
        media_meta = None
        file_path = None

        # Validation: media_file is required if is_collection is False
        if not is_collection and not media_file:
            raise ValueError("Media file is required when is_collection is False")

        # Validation: media_file should not be present if is_collection is True
        if is_collection and media_file:
            raise ValueError("Media file should not be provided when is_collection is True")

        # Validation: parent_id must follow hierarchy rules
        self._validate_parent_id(
            parent_id=parent_id,
            _is_collection=is_collection,
            entity_id=None,  # Creating new entity
        )

        # Extract metadata and save file if provided
        if media_file:
            # Extract metadata using MediaMetadataExtractor
            media_meta = self.metadata_extractor.extract_metadata(media_file, filename)

            # Check for duplicate MD5
            duplicate = self._check_duplicate_md5(media_meta.md5)
            if duplicate:
                # Return the existing item instead of raising an error
                return (self._entity_to_item(duplicate), True)  # is_duplicate=True

            # Save file to storage (convert Pydantic model to dict for storage)
            logger.debug(f"{filename} is sent for saving with metadata {media_meta.model_dump()}")
            file_path = self.file_storage.save_file(media_file, media_meta.model_dump(), filename)
            logger.debug(f"filepath received: {file_path}")
            logger.debug(self.file_storage.base_dir)

        # Extract metadata values from Pydantic model (or None for collections)
        if media_meta:
            file_size = media_meta.file_size
            height = media_meta.height
            width = media_meta.width
            duration = media_meta.duration
            mime_type = media_meta.mime_type
            type_str = media_meta.type
            extension = media_meta.extension
            md5 = media_meta.md5
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
            is_collection=is_collection,
            label=label,
            description=description,
            parent_id=parent_id,
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

        # Retry logic for database locks
        import time

        from sqlalchemy.exc import OperationalError

        max_retries = 5
        retry_delay = 0.1

        # Generate thumbnail if file was saved
        thumbnail_path = None
        if file_path:
            try:
                # Get absolute path for thumbnail generation
                abs_file_path = self.file_storage.get_absolute_path(file_path)
                thumbnail_path = ThumbnailGenerator.generate(str(abs_file_path), mime_type)
            except Exception as e:
                logger.error(f"Thumbnail generation failed (non-critical): {e}")

        for attempt in range(max_retries):
            try:
                self.db.add(entity)
                self.db.commit()
                self.db.refresh(entity)
                break  # Success, exit retry loop
            except IntegrityError as _:
                self.db.rollback()
                # Clean up file AND thumbnail if database insert failed
                if file_path:
                    _ = self.file_storage.delete_file(file_path)
                    # Cleanup thumbnail if generated
                    if thumbnail_path:
                        # thumbnail function returns partial path? No, docstring says output file path as string.
                        # Wait, ThumbnailGenerator.generate returns the OUTPUT PATH.
                        # So we need to delete that path directly.
                        # But wait, ThumbnailGenerator.delete takes the INPUT path and recalculates the thumbnail path.
                        # Let's use that for consistency.
                        abs_file_path = self.file_storage.get_absolute_path(file_path)
                        ThumbnailGenerator.delete(str(abs_file_path))

                raise DuplicateFileError(
                    f"Duplicate MD5 detected: {media_meta.md5 if media_meta else 'unknown'}"
                )
            except OperationalError as e:
                self.db.rollback()
                if "database is locked" in str(e).lower():
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Database locked during entity creation, "
                            f"retry {attempt + 1}/{max_retries} after {retry_delay}s"
                        )
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        logger.error(f"Database locked after {max_retries} retries, giving up")
                        # Clean up file AND thumbnail if all retries failed
                        if file_path:
                            _ = self.file_storage.delete_file(file_path)
                            abs_file_path = self.file_storage.get_absolute_path(file_path)
                            ThumbnailGenerator.delete(str(abs_file_path))
                        raise
                else:
                    # Re-raise if it's not a lock error
                    # Clean up file AND thumbnail if database error
                    if file_path:
                        _ = self.file_storage.delete_file(file_path)
                        abs_file_path = self.file_storage.get_absolute_path(file_path)
                        ThumbnailGenerator.delete(str(abs_file_path))
                    raise

        return (self._entity_to_item(entity), False)  # is_duplicate=False

    def update_entity(
        self,
        entity_id: int,
        is_collection: bool,
        label: str | None,
        description: str | None,
        parent_id: int | None,
        media_file: bytes | None,
        filename: str = "file",
        user_id: str | None = None,
    ) -> tuple[EntitySchema, bool] | None:
        """
        Fully update an existing entity (PUT) - file upload is optional for non-collections.

        Args:
            entity_id: Entity ID
            is_collection: Whether the entity is a collection
            label: Entity label
            description: Entity description
            parent_id: Parent entity ID
            media_file: Media file bytes (optional - if None, only metadata is updated)
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
        # The is_collection from the request should match the existing entity.is_collection
        if is_collection != entity.is_collection:
            raise ValueError(
                f"Cannot change is_collection from {entity.is_collection} to {is_collection}. "
                + "is_collection is immutable after entity creation."
            )

        # Validation: media_file should not be present if is_collection is True
        if entity.is_collection and media_file:
            raise ValueError("Media file should not be provided when is_collection is True")

        # Note: media_file is optional if is_collection is False (for PUT operations)
        # This allows updating metadata without changing the file
        file_path = None
        media_meta = None
        old_file_path = None
        if media_file:
            old_file_path = entity.file_path
            # Validation: parent_id must follow hierarchy rules
            self._validate_parent_id(
                parent_id=parent_id,
                _is_collection=entity.is_collection,  # Use existing is_collection (immutable)
                entity_id=entity_id,
            )

            # Extract metadata from new file
            media_meta = self.metadata_extractor.extract_metadata(media_file, filename)

            # Check for duplicate MD5 (excluding current entity)
            duplicate = self._check_duplicate_md5(media_meta.md5, exclude_entity_id=entity_id)
            if duplicate:
                # Raise error if this content already exists as a DIFFERENT entity
                raise DuplicateFileError(
                    f"File content matches existing entity {duplicate.id}. "
                    "Update would create a duplicate across entities."
                )
            
            # If MD5 is the same as current entity, we can potentially skip re-saving?
            # But the metadata (mime_type, width, etc.) might still be useful to update.
            # Currently we continue with saving for simplicity, but MD5 check above 
            # ensures we don't duplicate *across* entities.

            # Save new file (convert Pydantic model to dict for storage)
            file_path = self.file_storage.save_file(media_file, media_meta.model_dump(), filename)
            
            # Generate thumbnail for NEW file
            try:
                abs_file_path = self.file_storage.get_absolute_path(file_path)
                ThumbnailGenerator.generate(str(abs_file_path), media_meta.mime_type)
            except Exception as e:
                logger.error(f"Thumbnail generation failed for updated file (non-critical): {e}")

            # Update file metadata from Pydantic model
            entity.file_size = media_meta.file_size
            entity.height = media_meta.height
            entity.width = media_meta.width
            entity.duration = media_meta.duration
            entity.mime_type = media_meta.mime_type
            entity.type = media_meta.type
            entity.extension = media_meta.extension
            entity.md5 = media_meta.md5
            entity.file_path = file_path

        # Update entity with new metadata and client-provided fields
        now = self._now_timestamp()

        entity.label = label
        entity.description = description
        entity.parent_id = parent_id
        entity.updated_date = now
        entity.updated_by = user_id

        # Preserve old path for cleanup ON SUCCESS
        # If media_file was provided, old_file_path is set above 
        # but I need to make sure I capture it BEFORE updating entity.file_path
        # Wait, I already updated entity.file_path above.
        # Check logic:
        # Line 739: old_file_path = entity.file_path
        # Line 741: if old_file_path: _ = self.file_storage.delete_file(old_file_path)
        # ^ This was the OLD logic (delete immediately).
        # We need to change that.

        # CORRECT LOGIC:
        # capture old_file_path at the beginning of "if media_file:" block? Yes.
        # Oh, in the original code, old_file_path was captured at line 739.
        # But wait, my "TargetContent" block below starts from line 733.
        # So I need to structure the Replacement properly.

        # Let's be careful. The original code DELETES the old file at line 741.
        # I must DELETE that line from the original code and move the deletion to AFTER commit.

        try:
            self.db.commit()
            self.db.refresh(entity)
            
            # SUCCESS: Clean up OLD file and OLD thumbnail if file was replaced
            if old_file_path:
                try:
                    _ = self.file_storage.delete_file(old_file_path)
                    # Also delete OLD thumbnail
                    abs_old_path = self.file_storage.get_absolute_path(old_file_path)
                    ThumbnailGenerator.delete(str(abs_old_path))
                except Exception as e:
                    logger.warning(f"Failed to cleanup old file: {e}")

        except IntegrityError:
            self.db.rollback()
            # Clean up NEW file and NEW thumbnail if database update failed
            if file_path:
                _ = self.file_storage.delete_file(file_path)
                abs_file_path = self.file_storage.get_absolute_path(file_path)
                ThumbnailGenerator.delete(str(abs_file_path))
            
            raise DuplicateFileError(
                f"Duplicate MD5 detected: {media_meta.md5 if media_meta else ''}"
            )

        return (self._entity_to_item(entity), False)  # is_duplicate=False

    def ensure_thumbnail(self, entity: EntitySchema) -> str | None:
        """
        Ensure thumbnail exists for the entity. If not, generate it.
        Returns the absolute path to the thumbnail if allowed/generated.
        """
        if not entity.file_path:
            return None
            
        try:
            abs_file_path = self.file_storage.get_absolute_path(entity.file_path)
            thumb_path = ThumbnailGenerator.get_thumbnail_path(str(abs_file_path))
            
            if os.path.exists(thumb_path):
                return thumb_path
                
            # Generate if missing
            return ThumbnailGenerator.generate(str(abs_file_path), entity.mime_type)
        except Exception as e:
            logger.error(f"Failed to ensure thumbnail for entity {entity.id}: {e}")
            return None

    def patch_entity(
        self,
        entity_id: int,
        changes: dict[str, object] | None = None,
        user_id: str | None = None,
    ) -> EntitySchema | None:
        """
        Partially update an existing entity (PATCH).

        Args:
            entity_id: Entity ID
            changes: Dictionary of fields to update
            user_id: Optional user identifier from JWT (None in demo mode)

        Returns:
            Updated Item instance or None if not found
        """
        entity = self.db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            return None

        if changes is None:
            return self._entity_to_item(entity)

        # Validation: Check if parent_id is being modified
        if "parent_id" in changes:
            new_parent_id = cast(int | None, changes["parent_id"])

            # Validate the new parent_id (includes circular check and all other rules)
            self._validate_parent_id(
                parent_id=new_parent_id,
                _is_collection=entity.is_collection,
                entity_id=entity_id,
            )

        # Update provided fields
        for field_name, value in changes.items():
            if hasattr(entity, field_name):
                setattr(entity, field_name, value)

        entity.updated_date = self._now_timestamp()
        entity.updated_by = user_id

        self.db.commit()
        self.db.refresh(entity)

        return self._entity_to_item(entity)

    def delete_entity(self, entity_id: int) -> bool:
        """Permanently delete an entity (hard delete with full cleanup).

        This method implements the deletion orchestration as specified in DEL-01 to DEL-09:
        1. If entity is a collection, recursively delete all children
        2. For each child: soft-delete first (if not already), then hard delete
        3. Verify entity itself is soft-deleted (DEL-09 requirement)
        4. Delete all associated faces (DB + Vector + Files)
        5. Delete CLIP/DINO embeddings from vector stores
        6. Delete entity file from storage
        7. Clear MQTT retained messages
        8. Delete entity record from database

        Args:
            entity_id: Entity ID to delete

        Returns:
            True if entity was deleted, False if entity not found

        Raises:
            EntityNotSoftDeletedError: If entity is not soft-deleted (DEL-09)
            Exception: If deletion fails (DB will rollback)
        """
        try:
            # Get entity
            entity = self.db.query(Entity).filter(Entity.id == entity_id).first()
            if not entity:
                logger.warning(f"Entity {entity_id} not found for deletion")
                return False

            logger.info(f"Starting hard delete for entity {entity_id}")

            # Step 1: Handle collection children (DEL-06)
            if entity.is_collection:
                children = self.db.query(Entity).filter(Entity.parent_id == entity_id).all()
                logger.info(f"Entity {entity_id} is a collection with {len(children)} children")

                for child in children:
                    # If child not soft-deleted, soft-delete it first (for version history)
                    if not child.is_deleted:
                        logger.info(
                            f"Soft-deleting child {child.id} before hard delete "
                            f"(DEL-06 requirement)"
                        )
                        child.is_deleted = True
                        child.updated_date = self._now_timestamp()
                        self.db.flush()  # Ensure soft-delete is persisted

                    # Recursively hard-delete the child
                    logger.info(f"Recursively hard-deleting child {child.id}")
                    self.delete_entity(child.id)

            # Step 2: Verify entity is soft-deleted (DEL-09)
            if not entity.is_deleted:
                raise EntityNotSoftDeletedError(
                    f"Cannot hard delete entity {entity_id}: "
                    f"entity must be soft-deleted first (is_deleted=True). "
                    "Use PATCH /entities/{id} with is_deleted=true before hard deletion."
                )

            # Step 3: Delete all faces for this entity (DB + Vector + Files)
            if self.face_service:
                face_count = self.face_service.delete_faces_for_entity(entity_id)
                logger.debug(f"Deleted {face_count} faces for entity {entity_id}")
            else:
                logger.warning("FaceService not available, skipping face deletion")

            # Step 4: Delete CLIP embeddings from vector store
            if self.clip_store:
                try:
                    self.clip_store.delete_vector(entity_id)
                    logger.debug(f"Deleted CLIP embedding for entity {entity_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete CLIP embedding for entity {entity_id}: {e}")

            # Step 5: Delete DINO embeddings from vector store
            if self.dino_store:
                try:
                    self.dino_store.delete_vector(entity_id)
                    logger.debug(f"Deleted DINO embedding for entity {entity_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete DINO embedding for entity {entity_id}: {e}")

            # Step 6: Delete entity file from storage
            if entity.file_path:
                try:
                    deleted = self.file_storage.delete_file(entity.file_path)
                    
                    # Also delete thumbnail
                    abs_file_path = self.file_storage.get_absolute_path(entity.file_path)
                    ThumbnailGenerator.delete(str(abs_file_path))

                    if deleted:
                        logger.debug(f"Deleted entity file: {entity.file_path}")
                    else:
                        logger.warning(f"Entity file not found: {entity.file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete entity file {entity.file_path}: {e}")

            # Step 7: Clear MQTT retained message
            if self.broadcaster:
                try:
                    self.broadcaster.clear_entity_status(entity_id)
                    logger.debug(f"Cleared MQTT message for entity {entity_id}")
                except Exception as e:
                    logger.warning(f"Failed to clear MQTT message for entity {entity_id}: {e}")

            # Step 8: (Optional) Verify intelligence data cleanup (handled by cascade)
            # No manual action needed as FK has ON DELETE CASCADE

            # Step 9: Delete entity from database
            self.db.delete(entity)
            self.db.commit()
            logger.info(f"Successfully hard-deleted entity {entity_id}")
            return True

        except EntityNotSoftDeletedError:
            # Don't rollback for this validation error
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to delete entity {entity_id}: {e}")
            raise


