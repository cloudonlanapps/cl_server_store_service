from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from clmediakit import CLMetaData
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .schemas import BodyCreateEntity, BodyPatchEntity, BodyUpdateEntity, Item
from .models import Entity
from .file_storage import FileStorageService


class DuplicateFileError(Exception):
    """Raised when attempting to upload a file with duplicate MD5."""
    pass


class EntityService:
    """Service layer for entity operations."""
    
    def __init__(self, db: Session, base_dir: Optional[str] = None):
        """
        Initialize the entity service.
        
        Args:
            db: SQLAlchemy database session
            base_dir: Optional base directory for file storage (for testing)
        """
        self.db = db
        self.file_storage = FileStorageService(base_dir=base_dir)
       
    @staticmethod
    def _now_timestamp() -> int:
        """Return current UTC timestamp in milliseconds."""
        return int(datetime.now(timezone.utc).timestamp() * 1000)
    
    def _extract_metadata(self, file_bytes: bytes, filename: str = "file") -> Dict:
        """
        Extract metadata from file using CLMetaData.

        Args:
            file_bytes: File content as bytes
            filename: Original filename for extension detection

        Returns:
            Dictionary containing file metadata
        """
        import mimetypes

        # Create temporary file for CLMetaData processing
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = tmp_file.name

        try:
            # Extract metadata using CLMetaData
            try:
                cl_metadata = CLMetaData.from_media(tmp_path)
                metadata = cl_metadata.to_dict()
            except Exception as e:
                # If CLMetaData fails (e.g., invalid image), return minimal metadata with file size
                import hashlib
                print(f"Warning: CLMetaData extraction failed for {filename}: {e}")
                ext = Path(filename).suffix.lstrip('.').lower()
                mime_type, _ = mimetypes.guess_type(filename)

                # Compute MD5 hash for duplicate detection
                md5_hash = hashlib.md5(file_bytes).hexdigest()

                metadata = {
                    "extension": ext,
                    "FileSize": len(file_bytes),
                    "md5": md5_hash,
                }
                if mime_type:
                    metadata["MIMEType"] = mime_type

            # Ensure file size is always present (handle both FileSize and file_size keys)
            if "FileSize" not in metadata or not metadata["FileSize"]:
                metadata["FileSize"] = len(file_bytes)

            # Ensure MD5 is computed if not present
            if "md5" not in metadata or not metadata["md5"]:
                import hashlib
                metadata["md5"] = hashlib.md5(file_bytes).hexdigest()

            # Convert CreateDate to timestamp (ms) if present
            if "CreateDate" in metadata and metadata["CreateDate"]:
                try:
                    # Attempt to parse EXIF date format: YYYY:MM:DD HH:MM:SS
                    dt = datetime.strptime(str(metadata["CreateDate"]), "%Y:%m:%d %H:%M:%S")
                    metadata["CreateDate"] = int(dt.timestamp() * 1000)
                except ValueError:
                    # Fallback or ignore if format is different
                    pass

            return metadata
        finally:
            # Clean up temporary file
            Path(tmp_path).unlink(missing_ok=True)
    
    def _check_duplicate_md5(self, md5: str, exclude_entity_id: Optional[int] = None) -> Optional[Entity]:
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
        Convert SQLAlchemy Entity model to Pydantic Item schema.
        
        Args:
            entity: SQLAlchemy Entity instance
            
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
        version: Optional[int] = None,
        filter_param: Optional[str] = None, 
        search_query: Optional[str] = None
    ) -> Tuple[List[Item], int]:
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
        query = query.offset(offset).limit(page_size)
        
        entities = query.all()
        
        # If version is specified, get that version of each entity
        if version is not None:
            items = []
            for entity in entities:
                versioned_item = self.get_entity_version(entity.id, version)
                if versioned_item:  # Only include if version exists
                    items.append(versioned_item)
        else:
            items = [self._entity_to_item(entity) for entity in entities]
        
        return items, total_count
    
    def get_entity_by_id(self, entity_id: int, version: Optional[int] = None) -> Optional[Item]:
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
    
    def get_entity_version(self, entity_id: int, version: int) -> Optional[Item]:
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
        if hasattr(entity, 'versions'):
            versions_list = entity.versions.all()
            # Versions are 1-indexed for the API
            if 1 <= version <= len(versions_list):
                version_entity = versions_list[version - 1]
                return self._entity_to_item(version_entity)
        
        return None
    
    def get_entity_versions(self, entity_id: int) -> List[Dict]:
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
        
        if not hasattr(entity, 'versions'):
            return []
        
        versions_list = entity.versions.all()
        result = []
        for idx, version in enumerate(versions_list, start=1):
            version_info = {
                "version": idx,
                "transaction_id": version.transaction_id if hasattr(version, 'transaction_id') else None,
                "updated_date": version.updated_date if hasattr(version, 'updated_date') else None,
            }
            result.append(version_info)
        
        return result
    
    def create_entity(
        self, 
        body: BodyCreateEntity, 
        image: Optional[bytes] = None,
        filename: str = "file",
        user_id: Optional[str] = None
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
        file_meta = {}
        file_path = None

        # Validation: image is required if is_collection is False
        if not body.is_collection and not image:
            raise ValueError("Image is required when is_collection is False")
        
        # Validation: image should not be present if is_collection is True
        if body.is_collection and image:
            raise ValueError("Image should not be provided when is_collection is True")
        
        # Extract metadata and save file if provided
        if image:
            # Extract metadata using CLMetaData
            file_meta = self._extract_metadata(image, filename)

            # Check for duplicate MD5
            if file_meta.get("md5"):
                duplicate = self._check_duplicate_md5(file_meta["md5"])
                if duplicate:
                    # Return the existing item instead of raising an error
                    return self._entity_to_item(duplicate)

            # Save file to storage
            file_path = self.file_storage.save_file(image, file_meta, filename)
        
        entity = Entity(
            is_collection=body.is_collection,
            label=body.label,
            description=body.description,
            parent_id=body.parent_id,
            added_date=now,
            updated_date=now,
            create_date=now,
            file_size=file_meta.get("FileSize"),
            height=file_meta.get("ImageHeight"),
            width=file_meta.get("ImageWidth"),
            duration=file_meta.get("Duration"),
            mime_type=file_meta.get("MIMEType"),
            type=file_meta.get("type"),
            extension=file_meta.get("extension"),
            md5=file_meta.get("md5"),
            file_path=file_path,
            is_deleted=False,
            added_by=user_id,
            updated_by=user_id,
        )
        
        try:
            self.db.add(entity)
            self.db.commit()
            self.db.refresh(entity)
        except IntegrityError as e:
            self.db.rollback()
            # Clean up file if database insert failed
            if file_path:
                self.file_storage.delete_file(file_path)
            raise DuplicateFileError(f"Duplicate MD5 detected: {file_meta.get('md5')}")
        
        return self._entity_to_item(entity)
    
    def update_entity(
        self, 
        entity_id: int, 
        body: BodyUpdateEntity,
        image: bytes,
        filename: str = "file",
        user_id: Optional[str] = None
    ) -> Optional[Item]:
        """
        Fully update an existing entity (PUT) - requires file upload.
        
        Args:
            entity_id: Entity ID
            body: Entity update data
            image: Image file bytes (mandatory for PUT)
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
                "is_collection is immutable after entity creation."
            )
        
        # Validation: image should not be present if is_collection is True
        if entity.is_collection and image:
            raise ValueError("Image should not be provided when is_collection is True")
        
        # Note: image is optional if is_collection is False (for PUT operations)
        # This allows updating metadata without changing the file
        
        if image:
            # Extract metadata from new file
            file_meta = self._extract_metadata(image, filename)

            # Check for duplicate MD5 (excluding current entity)
            if file_meta.get("md5"):
                duplicate = self._check_duplicate_md5(file_meta["md5"], exclude_entity_id=entity_id)
                if duplicate:
                    # Return the existing item instead of raising an error
                    return self._entity_to_item(duplicate)

            # Delete old file if exists
            old_file_path = entity.file_path
            if old_file_path:
                self.file_storage.delete_file(old_file_path)

            # Save new file
            file_path = self.file_storage.save_file(image, file_meta, filename)
                   
            # Update file metadata
            entity.file_size = file_meta.get("FileSize")
            entity.height = file_meta.get("ImageHeight")
            entity.width = file_meta.get("ImageWidth")
            entity.duration = file_meta.get("Duration")
            entity.mime_type = file_meta.get("MIMEType")
            entity.type = file_meta.get("type")
            entity.extension = file_meta.get("extension")
            entity.md5 = file_meta.get("md5")
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
                self.file_storage.delete_file(file_path)
            raise DuplicateFileError(f"Duplicate MD5 detected: {file_meta.get('md5')}")
        
        return self._entity_to_item(entity)
    
    def patch_entity(self, entity_id: int, body: BodyPatchEntity, user_id: Optional[str] = None) -> Optional[Item]:
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
        
        # Update only provided fields
        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(entity, field, value)
        
        entity.updated_date = self._now_timestamp()
        entity.updated_by = user_id
        
        self.db.commit()
        self.db.refresh(entity)
        
        return self._entity_to_item(entity)
    
    def delete_entity(self, entity_id: int) -> Optional[Item]:
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
            self.file_storage.delete_file(entity.file_path)
            
        self.db.delete(entity)
        self.db.commit()
        
        return self._entity_to_item(entity)
    
    def delete_all_entities(self) -> None:
        """Delete all entities from the database."""
        self.db.query(Entity).delete()
        self.db.commit()
