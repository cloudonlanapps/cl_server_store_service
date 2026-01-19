from __future__ import annotations

from datetime import UTC, datetime

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import StoreConfig

from cl_ml_tools.plugins.face_detection.schema import BBox, FaceLandmarks
from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .entity_storage import EntityStorageService
from .media_metadata import MediaMetadataExtractor
from .models import Entity
from .qdrant_image_store import SearchPreferences
from .schemas import (
    BodyCreateEntity,
    BodyPatchEntity,
    BodyUpdateEntity,
    EntityJobResponse,
    FaceMatchResult,
    FaceResponse,
    Item,
    KnownPersonResponse,
    SimilarFacesResult,
    SimilarImageResult,
)


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
        self.file_storage: EntityStorageService = EntityStorageService(
            base_dir=str(config.media_storage_dir)
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

    def _validate_parent_id(
        self,
        parent_id: int | None,
        is_collection: bool,
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
            raise ValueError(
                f"Cannot set parent_id to {parent_id}: parent entity does not exist"
            )

        # Rule: Parent must be a collection
        if not parent.is_collection:
            raise ValueError(
                f"Cannot set parent_id to {parent_id}: parent entity must be a collection. "
                f"Entity {parent_id} is not a collection."
            )

        # Rule: Parent must not be soft-deleted
        if parent.is_deleted:
            raise ValueError(
                f"Cannot set parent_id to {parent_id}: parent entity is deleted"
            )

        # Rule: Prevent circular hierarchies (only for updates)
        if entity_id is not None:
            current_parent = parent_id
            visited = {entity_id}
            while current_parent is not None:
                if current_parent in visited:
                    raise ValueError(
                        f"Circular hierarchy detected: entity {parent_id} is already "
                        f"a descendant of {entity_id}"
                    )
                visited.add(current_parent)
                parent_entity = (
                    self.db.query(Entity).filter(Entity.id == current_parent).first()
                )
                current_parent = parent_entity.parent_id if parent_entity else None

        # Rule: Max hierarchy depth check (max 10 levels)
        if parent_id is not None:
            depth = 1  # Starting at depth 1 (the parent)
            current_check = parent_id
            while current_check is not None:
                parent_ent = (
                    self.db.query(Entity).filter(Entity.id == current_check).first()
                )
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

    def _entity_to_item(self, entity: Entity) -> Item:
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
        )

    def get_entities(
        self,
        page: int = 1,
        page_size: int = 20,
        version: int | None = None,
        filter_param: str | None = None,  # pyright: ignore[reportUnusedParameter]
        search_query: str | None = None,  # pyright: ignore[reportUnusedParameter]
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
        query = self.db.query(Entity)

        # Apply deleted filter
        if exclude_deleted:
            query = query.filter(Entity.is_deleted == False)  # noqa: E712

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
                version_entity = versions_list[  # pyright: ignore[reportAny]
                    version - 1
                ]
                return self._entity_to_item(
                    version_entity  # pyright: ignore[reportAny]
                )

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
        for idx, version in enumerate(  # pyright: ignore[reportAny]
            versions_list, start=1
        ):
            version_info: dict[str, int | None] = {
                "version": idx,
                "transaction_id": (
                    version.transaction_id  # pyright: ignore[reportAny]
                    if hasattr(version, "transaction_id")  # pyright: ignore[reportAny]
                    else None
                ),
                "updated_date": (
                    version.updated_date  # pyright: ignore[reportAny]
                    if hasattr(version, "updated_date")  # pyright: ignore[reportAny]
                    else None
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

        # Validation: parent_id must follow hierarchy rules
        self._validate_parent_id(
            parent_id=body.parent_id,
            is_collection=body.is_collection,
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
                return self._entity_to_item(duplicate)

            # Save file to storage (convert Pydantic model to dict for storage)
            logger.error(f"{filename} is sent for saving with metadata {file_meta.model_dump()}")
            file_path = self.file_storage.save_file(image, file_meta.model_dump(), filename)
            logger.error(f"filepath received: {file_path}")
            logger.error(self.file_storage.base_dir)

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
            # Validation: parent_id must follow hierarchy rules
            self._validate_parent_id(
                parent_id=body.parent_id,
                is_collection=entity.is_collection,  # Use existing is_collection (immutable)
                entity_id=entity_id,
            )

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

        # Validation: Check if parent_id is being modified
        patch_fields = body.model_dump(exclude_unset=True)
        if "parent_id" in patch_fields:
            new_parent_id = body.parent_id

            # Validate the new parent_id (includes circular check and all other rules)
            self._validate_parent_id(
                parent_id=new_parent_id,
                is_collection=entity.is_collection,
                entity_id=entity_id,
            )

        # Update only provided fields (get values from Pydantic model to preserve types)
        patch_fields = body.model_dump(exclude_unset=True)
        for field_name in patch_fields:
            value = getattr(body, field_name)
            setattr(entity, field_name, value)

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

        # Prevent deletion if entity has children
        children_count = self.db.query(Entity).filter(Entity.parent_id == entity_id).count()
        if children_count > 0:
            raise ValueError(
                f"Cannot delete entity {entity_id}: it has {children_count} child(ren). "
                "Delete or move the children first."
            )

        # Hard delete: remove file and database record
        if entity.file_path:
            _ = self.file_storage.delete_file(entity.file_path)

        self.db.delete(entity)
        _ = self.db.commit()

        return self._entity_to_item(entity)

    async def trigger_async_jobs(self, entity: Entity) -> dict[str, str | None]:
        """Trigger async face detection and embedding jobs for an image entity.

        Only processes images (not collections). Submits jobs to compute service
        and returns immediately without blocking.

        Args:
            entity: Entity instance to process

        Returns:
            Dict with job IDs: {"face_detection_job": job_id, "clip_embedding_job": job_id}
            Returns None for job_id if job submission fails or entity is not an image.
        """
        # Only process images
        if entity.is_collection or entity.type != "image":
            logger.debug(
                f"Skipping job submission for entity {entity.id}: "
                + f"is_collection={entity.is_collection}, type={entity.type}"
            )
            return {"face_detection_job": None, "clip_embedding_job": None}

        # Get absolute file path
        if not entity.file_path:
            logger.warning(f"Entity {entity.id} has no file_path")
            return {"face_detection_job": None, "clip_embedding_job": None}

        absolute_path = self.file_storage.get_absolute_path(entity.file_path)
        if not absolute_path.exists():
            logger.warning(f"File not found for entity {entity.id}: {absolute_path}")
            return {"face_detection_job": None, "clip_embedding_job": None}

        # Get singletons
        from .compute_singleton import get_compute_client
        from .job_callbacks import JobCallbackHandler
        from .job_service import JobSubmissionService
        from .qdrant_singleton import get_qdrant_store

        compute_client = get_compute_client()
        qdrant_store = get_qdrant_store()

        # Create handlers with job_service and config
        job_service = JobSubmissionService(compute_client)
        callback_handler = JobCallbackHandler(
            compute_client,
            qdrant_store,
            config=self.config,
            job_submission_service=job_service,
        )

        # Define callbacks with proper typing
        from cl_client.models import JobResponse

        async def face_detection_callback(job: JobResponse) -> None:
            """Handle face detection job completion."""
            job_service.update_job_status(job.job_id, job.status, job.error_message)
            if job.status == "completed":
                await callback_handler.handle_face_detection_complete(entity.id, job)

        async def clip_embedding_callback(job: JobResponse) -> None:
            """Handle CLIP embedding job completion."""
            job_service.update_job_status(job.job_id, job.status, job.error_message)
            if job.status == "completed":
                await callback_handler.handle_clip_embedding_complete(entity.id, job)

        # Submit jobs
        face_job_id = await job_service.submit_face_detection(
            entity_id=entity.id,
            file_path=str(absolute_path),
            on_complete_callback=face_detection_callback,
        )

        clip_job_id = await job_service.submit_clip_embedding(
            entity_id=entity.id,
            file_path=str(absolute_path),
            on_complete_callback=clip_embedding_callback,
        )

        logger.info(
            f"Submitted jobs for entity {entity.id}: "
            + f"face_detection={face_job_id}, clip_embedding={clip_job_id}"
        )

        return {
            "face_detection_job": face_job_id,
            "clip_embedding_job": clip_job_id,
        }

    def delete_all_entities(self) -> None:
        """Delete all entities from the database."""
        _ = self.db.query(Entity).delete()
        _ = self.db.commit()

    def get_entity_faces(self, entity_id: int) -> list[FaceResponse]:
        """Get all faces detected in an entity.

        Args:
            entity_id: Entity ID

        Returns:
            List of FaceResponse schemas with parsed bbox and landmarks
        """

        from . import schemas
        from .models import Face

        faces = self.db.query(Face).filter(Face.entity_id == entity_id).all()

        results: list[schemas.FaceResponse] = []
        for face in faces:
            results.append(
                schemas.FaceResponse(
                    id=face.id,
                    entity_id=face.entity_id,
                    bbox=BBox.model_validate_json(face.bbox),
                    confidence=face.confidence,
                    landmarks=FaceLandmarks.model_validate_json(face.landmarks),
                    file_path=face.file_path,
                    created_at=face.created_at,
                    known_person_id=face.known_person_id,
                )
            )

        return results

    def get_entity_jobs(self, entity_id: int) -> list[EntityJobResponse]:
        """Get all jobs for an entity.

        Args:
            entity_id: Entity ID

        Returns:
            List of EntityJobResponse schemas
        """
        from . import schemas
        from .models import EntityJob

        jobs = self.db.query(EntityJob).filter(EntityJob.entity_id == entity_id).all()

        results: list[schemas.EntityJobResponse] = []
        for job in jobs:
            results.append(
                schemas.EntityJobResponse(
                    id=job.id,
                    entity_id=job.entity_id,
                    job_id=job.job_id,
                    task_type=job.task_type,
                    status=job.status,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    completed_at=job.completed_at,
                    error_message=job.error_message,
                )
            )

        return results

    def search_similar_images(
        self, entity_id: int, limit: int = 5, score_threshold: float = 0.85
    ) -> list[SimilarImageResult]:
        """Search for similar images using CLIP embeddings.

        Args:
            entity_id: Query entity ID (must have embedding in Qdrant)
            limit: Maximum number of results to return
            score_threshold: Minimum similarity score [0.0, 1.0]

        Returns:
            List of SimilarImageResult schemas
        """
        from . import schemas
        from .qdrant_singleton import get_qdrant_store

        qdrant_store = get_qdrant_store()

        # Get the query embedding from Qdrant
        query_point = qdrant_store.get_vector(entity_id)
        if not query_point:
            logger.warning(f"No embedding found for entity {entity_id}")
            return []

        query_vector = query_point.embedding

        # Search for similar images
        results = qdrant_store.search(
            query_vector=query_vector,
            limit=limit + 1,  # +1 because query itself will be in results
            search_options=SearchPreferences(
                with_payload=True,
                score_threshold=score_threshold,
            ),
        )

        # Filter out the query entity itself and convert to Pydantic
        filtered_results: list[SimilarImageResult] = []
        for result in results:
            if result.id != entity_id:
                filtered_results.append(
                    schemas.SimilarImageResult(
                        entity_id=int(result.id),  # type: ignore[arg-type]
                        score=float(result.score),
                        entity=None,  # Will be populated by route handler if requested
                    )
                )

        return filtered_results[:limit]

    def get_known_person(self, person_id: int) -> KnownPersonResponse | None:
        """Get known person details.

        Args:
            person_id: Known person ID

        Returns:
            KnownPersonResponse schema or None if not found
        """
        from . import schemas
        from .models import Face, KnownPerson

        person = self.db.query(KnownPerson).filter(KnownPerson.id == person_id).first()
        if not person:
            return None

        # Count faces for this person
        face_count = self.db.query(Face).filter(Face.known_person_id == person_id).count()

        return schemas.KnownPersonResponse(
            id=person.id,
            name=person.name,
            created_at=person.created_at,
            updated_at=person.updated_at,
            face_count=face_count,
        )

    def get_all_known_persons(self) -> list[KnownPersonResponse]:
        """Get all known persons.

        Returns:
            List of KnownPersonResponse schemas
        """
        from . import schemas
        from .models import Face, KnownPerson

        persons = self.db.query(KnownPerson).all()

        results: list[schemas.KnownPersonResponse] = []
        for person in persons:
            # Count faces for this person
            face_count = self.db.query(Face).filter(Face.known_person_id == person.id).count()

            results.append(
                schemas.KnownPersonResponse(
                    id=person.id,
                    name=person.name,
                    created_at=person.created_at,
                    updated_at=person.updated_at,
                    face_count=face_count,
                )
            )

        return results

    def get_known_person_faces(self, person_id: int) -> list[FaceResponse]:
        """Get all faces for a known person.

        Args:
            person_id: Known person ID

        Returns:
            List of FaceResponse schemas
        """

        from . import schemas
        from .models import Face

        faces = self.db.query(Face).filter(Face.known_person_id == person_id).all()

        results: list[schemas.FaceResponse] = []
        for face in faces:
            results.append(
                schemas.FaceResponse(
                    id=face.id,
                    entity_id=face.entity_id,
                    bbox=BBox.model_validate_json(face.bbox),
                    confidence=face.confidence,
                    landmarks=FaceLandmarks.model_validate_json(face.landmarks),
                    file_path=face.file_path,
                    created_at=face.created_at,
                    known_person_id=face.known_person_id,
                )
            )

        return results

    def update_known_person_name(self, person_id: int, name: str) -> KnownPersonResponse | None:
        """Update known person name.

        Args:
            person_id: Known person ID
            name: New name for the person

        Returns:
            Updated KnownPersonResponse schema or None if not found
        """
        from .models import KnownPerson

        person = self.db.query(KnownPerson).filter(KnownPerson.id == person_id).first()
        if not person:
            return None

        person.name = name
        person.updated_at = self._now_timestamp()

        self.db.commit()
        self.db.refresh(person)

        return self.get_known_person(person_id)

    def get_face_matches(self, face_id: int) -> list[FaceMatchResult]:
        """Get all match records for a face.

        Args:
            face_id: Face ID

        Returns:
            List of FaceMatchResult schemas
        """

        from . import schemas
        from .models import Face, FaceMatch

        matches = self.db.query(FaceMatch).filter(FaceMatch.face_id == face_id).all()

        results: list[schemas.FaceMatchResult] = []
        for match in matches:
            # Optionally load matched face details
            matched_face = self.db.query(Face).filter(Face.id == match.matched_face_id).first()
            matched_face_response = None
            if matched_face:
                matched_face_response = schemas.FaceResponse(
                    id=matched_face.id,
                    entity_id=matched_face.entity_id,
                    bbox=BBox.model_validate_json(matched_face.bbox),
                    confidence=matched_face.confidence,
                    landmarks=FaceLandmarks.model_validate_json(matched_face.landmarks),
                    file_path=matched_face.file_path,
                    created_at=matched_face.created_at,
                    known_person_id=matched_face.known_person_id,
                )

            results.append(
                schemas.FaceMatchResult(
                    id=match.id,
                    face_id=match.face_id,
                    matched_face_id=match.matched_face_id,
                    similarity_score=match.similarity_score,
                    created_at=match.created_at,
                    matched_face=matched_face_response,
                )
            )

        return results

    def search_similar_faces_by_id(
        self, face_id: int, limit: int = 5, threshold: float = 0.7
    ) -> list[SimilarFacesResult]:
        """Search for similar faces using face store.

        Args:
            face_id: Query face ID (must have embedding in face store)
            limit: Maximum number of results to return
            threshold: Minimum similarity score [0.0, 1.0]

        Returns:
            List of SimilarFacesResult schemas
        """

        from . import schemas
        from .face_store_singleton import get_face_store
        from .models import Face

        face_store = get_face_store()

        # Get the query embedding from face store
        query_points = face_store.get_vector(face_id)
        if not query_points:
            logger.warning(f"No embedding found for face {face_id}")
            return []

        # Search for similar faces
        results = face_store.search(
            query_vector=query_points.embedding,
            limit=limit + 1,  # +1 because query itself will be in results
            search_options=SearchPreferences(
                with_payload=True,
                score_threshold=threshold,
            ),
        )

        # Filter out the query face itself and convert to Pydantic
        filtered_results: list[schemas.SimilarFacesResult] = []
        for result in results:
            if result.id != face_id:
                # Optionally load face details
                face = self.db.query(Face).filter(Face.id == result.id).first()
                face_response = None
                if face:
                    face_response = schemas.FaceResponse(
                        id=face.id,
                        entity_id=face.entity_id,
                        bbox=BBox.model_validate_json(face.bbox),
                        confidence=face.confidence,
                        landmarks=FaceLandmarks.model_validate_json(face.landmarks),
                        file_path=face.file_path,
                        created_at=face.created_at,
                        known_person_id=face.known_person_id,
                    )

                filtered_results.append(
                    schemas.SimilarFacesResult(
                        face_id=int(result.id),  # type: ignore[arg-type]
                        score=float(result.score),
                        known_person_id=(
                            result.payload.get("known_person_id") if result.payload else None
                        ),
                        face=face_response,
                    )
                )

        return filtered_results[:limit]
