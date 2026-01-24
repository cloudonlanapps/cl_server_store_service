from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from store.common import schemas
from store.common.models import Entity, ImageIntelligence
from store.common.schemas import (
    BodyCreateEntity,
    BodyPatchEntity,
    BodyUpdateEntity,
    Item,
)

from ..common.storage import StorageService
from .config import StoreConfig
from .media_metadata import MediaMetadataExtractor


class DuplicateFileError(Exception):
    """Raised when attempting to upload a file with duplicate MD5."""

    pass


class EntityService:
    """Service layer for entity operations."""

    def __init__(self, db: Session, config: StoreConfig):
        """Initialize the entity service.

        Args:
            db: SQLAlchemy database session
            config: Store configuration
        """
        self.db: Session = db
        self.config: StoreConfig = config
        # Use media_storage_dir from config for entity files (organized by date)
        self.file_storage: StorageService = StorageService(base_dir=str(config.media_storage_dir))
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

    def _entity_to_item(self, entity: Entity, intelligence_status: str | None = None) -> Item:
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
            is_indirectly_deleted=self._check_ancestor_deleted(entity),
            intelligence_status=intelligence_status,
        )

    def get_entities(
        self,
        page: int = 1,
        page_size: int = 20,
        version: int | None = None,
        filter_param: str | None = None,
        search_query: str | None = None,
        exclude_deleted: bool = False,
    ) -> tuple[list[Item], int]:
        """
        Retrieve all entities with optional pagination and versioning.

        Args:
            page: Page number (1-indexed)
            page_size: Number of items per page
            version: Optional version number to retrieve for all entities
            filter_param: Optional filter string (not implemented yet)
            search_query: Optional search query (not implemented yet)
            exclude_deleted: Whether to exclude soft-deleted entities (default: False)

        Returns:
            Tuple of (items, total_count)
        """
        _ = filter_param
        _ = search_query
        # Join with ImageIntelligence to get status
        query = self.db.query(Entity, ImageIntelligence.status).outerjoin(
            ImageIntelligence, Entity.id == ImageIntelligence.entity_id
        )

        # Apply deleted filter
        if exclude_deleted:
            query = query.filter(Entity.is_deleted == False)  # noqa: E712

        # TODO: Implement filtering and search logic

        # Get total count before pagination
        total_count = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.order_by(Entity.id.asc()).offset(offset).limit(page_size)

        results = cast(list[tuple[Entity, str | None]], query.all())

        # If version is specified, get that version of each entity
        if version is not None:
            items_list: list[Item] = []
            for entity, _ in results:
                versioned_item = self.get_entity_version(entity.id, version)
                if versioned_item:  # Only include if version exists
                    items_list.append(versioned_item)
            return items_list, total_count

        items: list[Item] = []
        for entity, status in results:
            items.append(self._entity_to_item(entity, intelligence_status=status))

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

        result = cast(
            tuple[Entity, str | None] | None,
            self.db.query(Entity, ImageIntelligence.status)
            .outerjoin(ImageIntelligence, Entity.id == ImageIntelligence.entity_id)
            .filter(Entity.id == entity_id)
            .first(),
        )

        if result:
            entity, status = result
            return self._entity_to_item(entity, intelligence_status=status)
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
            versions_list = cast(list[Entity], entity.versions.all())  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
            # Versions are 1-indexed for the API
            if 1 <= version <= len(versions_list):
                version_entity = versions_list[version - 1]
                return self._entity_to_item(version_entity)

        return None

    def get_entity_versions(self, entity_id: int) -> list[schemas.VersionInfo]:
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
        result: list[schemas.VersionInfo] = []
        for idx, version in enumerate(versions_list, start=1):  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
            # SQLAlchemy-Continuum version objects can be validated via model_validate
            # with from_attributes=True enabled in the schema
            # Create dictionary with required fields
            version_data = {  # pyright: ignore[reportUnknownVariableType]
                "transaction_id": version.transaction_id,  # pyright: ignore[reportUnknownMemberType]
                "updated_date": version.updated_date,  # pyright: ignore[reportUnknownMemberType]
                "version": idx,
            }
            version_info = schemas.VersionInfo.model_validate(version_data)
            result.append(version_info)

        return result

    def create_entity(
        self,
        body: BodyCreateEntity,
        image: bytes | None = None,
        filename: str = "file",
        user_id: str | None = None,
    ) -> tuple[Item, bool]:
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

        # Validation: parent_id must follow hierarchy rules
        self._validate_parent_id(
            parent_id=body.parent_id,
            _is_collection=body.is_collection,
            entity_id=None,  # Creating new entity
        )

        # Extract metadata and save file if provided
        if image:
            # Extract metadata using MediaMetadataExtractor
            file_meta = self.metadata_extractor.extract_metadata(image, filename)

            # Check for duplicate MD5
            duplicate = self._check_duplicate_md5(file_meta.md5)
            if duplicate:
                # Return the existing item instead of raising an error
                return (self._entity_to_item(duplicate), True)  # is_duplicate=True

            # Save file to storage (convert Pydantic model to dict for storage)
            logger.debug(f"{filename} is sent for saving with metadata {file_meta.model_dump()}")
            file_path = self.file_storage.save_file(image, file_meta.model_dump(), filename)
            logger.debug(f"filepath received: {file_path}")
            logger.debug(self.file_storage.base_dir)

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

        # Retry logic for database locks
        import time

        from sqlalchemy.exc import OperationalError

        max_retries = 5
        retry_delay = 0.1

        for attempt in range(max_retries):
            try:
                self.db.add(entity)
                self.db.commit()
                self.db.refresh(entity)
                break  # Success, exit retry loop
            except IntegrityError as _:
                self.db.rollback()
                # Clean up file if database insert failed
                if file_path:
                    _ = self.file_storage.delete_file(file_path)
                raise DuplicateFileError(
                    f"Duplicate MD5 detected: {file_meta.md5 if file_meta else 'unknown'}"
                )
            except OperationalError as e:
                self.db.rollback()
                if "database is locked" in str(e).lower():
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Database locked during entity creation, retry {attempt + 1}/{max_retries} after {retry_delay}s"
                        )
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        logger.error(f"Database locked after {max_retries} retries, giving up")
                        raise
                else:
                    # Re-raise if it's not a lock error
                    raise

        return (self._entity_to_item(entity), False)  # is_duplicate=False

    def update_entity(
        self,
        entity_id: int,
        body: BodyUpdateEntity,
        image: bytes | None,
        filename: str = "file",
        user_id: str | None = None,
    ) -> tuple[Item, bool] | None:
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
            # Validation: parent_id must follow hierarchy rules
            self._validate_parent_id(
                parent_id=body.parent_id,
                _is_collection=entity.is_collection,  # Use existing is_collection (immutable)
                entity_id=entity_id,
            )

            # Extract metadata from new file
            file_meta = self.metadata_extractor.extract_metadata(image, filename)

            # Check for duplicate MD5 (excluding current entity)
            duplicate = self._check_duplicate_md5(file_meta.md5, exclude_entity_id=entity_id)
            if duplicate:
                # Return the existing item instead of raising an error
                return (self._entity_to_item(duplicate), True)  # is_duplicate=True

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

        return (self._entity_to_item(entity), False)  # is_duplicate=False

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

        # Validation: Check if parent_id is being modified
        patch_fields = body.model_dump(exclude_unset=True)
        if "parent_id" in patch_fields:
            new_parent_id = body.parent_id

            # Validate the new parent_id (includes circular check and all other rules)
            self._validate_parent_id(
                parent_id=new_parent_id,
                _is_collection=entity.is_collection,
                entity_id=entity_id,
            )

        # Update only provided fields (get values from Pydantic model to preserve types)
        patch_fields = body.model_dump(exclude_unset=True)
        for field_name in patch_fields:
            value = cast(object, getattr(body, field_name))
            setattr(entity, field_name, value)

        entity.updated_date = self._now_timestamp()
        entity.updated_by = user_id

        self.db.commit()
        self.db.refresh(entity)

        return self._entity_to_item(entity)

    def delete_entity(self, entity_id: int, *, _from_parent: bool = False) -> bool:
        """
        Delete an entity (hard delete with proper versioning).

        When called directly (from API route):
        - Entity MUST already be soft-deleted, otherwise raises ValueError
        - Recursively soft-deletes and hard-deletes all children

        When called recursively (from parent's deletion):
        - Auto-soft-deletes the entity if not already soft-deleted
        - Then proceeds with hard deletion

        Args:
            entity_id: Entity ID
            _from_parent: Internal flag indicating this is a recursive call from parent deletion

        Returns:
            True if entity was deleted, False if entity not found

        Raises:
            ValueError: If entity is not soft-deleted (only for direct calls)
        """
        entity = self.db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            return False

        # Direct call: require entity to be soft-deleted first
        if not _from_parent and not entity.is_deleted:
            raise ValueError(
                f"Cannot delete entity {entity_id}: entity must be soft-deleted first. "
                + "Call soft_delete_entity() before deletion."
            )

        # Recursive call from parent: soft-delete if not already
        if _from_parent and not entity.is_deleted:
            entity.is_deleted = True
            self.db.commit()  # Create version record

        # Recursively handle children if this is a collection
        children = self.db.query(Entity).filter(Entity.parent_id == entity_id).all()
        if children:
            for child in children:
                # Recursively delete child (will auto-soft-delete via _from_parent=True)
                _ = self.delete_entity(child.id, _from_parent=True)

        # Hard delete this entity - remove file and database record
        if entity.file_path:
            _ = self.file_storage.delete_file(entity.file_path)

        self.db.delete(entity)
        self.db.commit()

        return True

    def soft_delete_entity(self, entity_id: int) -> Item | None:
        """
        Soft delete an entity (mark as deleted without removing).

        This creates a version record with is_deleted=True for audit trail.
        The entity remains in the database but is marked as deleted.

        Note: This does NOT soft-delete children. Children must be explicitly
        soft-deleted or will be soft-deleted automatically during hard deletion.

        Args:
            entity_id: Entity ID

        Returns:
            Soft-deleted Item instance or None if not found
        """
        entity = self.db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            return None

        # Mark as soft-deleted
        entity.is_deleted = True
        self.db.commit()

        return self._entity_to_item(entity)

    def delete_all_entities(self) -> None:
        """Delete all entities and related data from the database."""
        # This is used for cleanup in tests/admin
        from sqlalchemy import text

        from ..common.models import (
            Entity,
            EntityJob,
            EntitySyncState,
            Face,
            FaceMatch,
            ImageIntelligence,
            KnownPerson,
        )

        # 1. Clear intelligence and related tables
        _ = self.db.query(EntityJob).delete()
        _ = self.db.query(FaceMatch).delete()
        _ = self.db.query(Face).delete()
        _ = self.db.query(ImageIntelligence).delete()
        _ = self.db.query(KnownPerson).delete()

        # 2. Clear versioning and transaction metadata (using raw SQL for Continuum tables)
        # Sequence of deletion matters for FKs
        tables_to_clear = [
            "entities_version",
            "known_persons_version",
            "transaction_changes",
            "transaction",
        ]
        for table in tables_to_clear:
            try:
                _ = self.db.execute(text(f"DELETE FROM {table}"))
            except Exception as e:
                logger.warning(f"Failed to clear Continuum table {table}: {e}")

        # 3. Delete all records from main Entity table
        _ = self.db.query(Entity).delete()

        # 4. Reset sync state and sequences
        sync_state = self.db.query(EntitySyncState).filter(EntitySyncState.id == 1).first()
        if sync_state:
            sync_state.last_version = 0

        try:
            _ = self.db.execute(text("DELETE FROM sqlite_sequence"))
        except Exception as e:
            logger.debug(
                f"Note: sqlite_sequence clear failed (common if no AUTOINCREMENT used yet): {e}"
            )

        self.db.commit()
