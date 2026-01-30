"""Service for face lifecycle management (DB + Vector + File deletion)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy.orm import Session

from store.db_service import DBService
from store.db_service.db_internals import Entity, Face
from store.db_service.schemas import EntityIntelligenceData
from store.vectorstore_services.vector_stores import QdrantVectorStore

if TYPE_CHECKING:
    from ..common.storage import StorageService


class FaceService:
    """Service layer for face deletion operations."""

    def __init__(
        self,
        db: Session,
        db_service: DBService,
        face_store: QdrantVectorStore,
        storage_service: StorageService,
    ):
        """Initialize the face service.

        Args:
            db: SQLAlchemy database session
            db_service: DBService for high-level operations
            face_store: Qdrant vector store for face embeddings
            storage_service: Storage service for face crop files
        """
        self.db: Session = db
        self.db_service: DBService = db_service
        self.face_store: QdrantVectorStore = face_store
        self.storage_service: StorageService = storage_service

    def delete_face(self, face_id: int) -> bool:
        """Delete a single face completely (DB + Vector + File).

        This method:
        1. Retrieves face details from DB
        2. Deletes face vector from Qdrant
        3. Deletes face crop file from storage
        4. Deletes face record from DB
        5. Decrements face_count in parent Entity intelligence_data

        Args:
            face_id: Face ID to delete

        Returns:
            True if face was deleted, False if face not found

        Raises:
            Exception: If deletion fails (DB will rollback)
        """
        try:
            # Step 1: Get face details
            face = self.db.query(Face).filter(Face.id == face_id).first()
            if not face:
                logger.warning(f"Face {face_id} not found for deletion")
                return False

            entity_id = face.entity_id
            file_path = face.file_path

            logger.info(f"Deleting face {face_id} for entity {entity_id}")

            # Step 2: Delete from Vector Store (Qdrant)
            try:
                self.face_store.delete_vector(face_id)
                logger.debug(f"Deleted face {face_id} from vector store")
            except Exception as e:
                logger.warning(f"Failed to delete face {face_id} from vector store: {e}")
                # Continue with deletion even if vector delete fails (orphan cleanup will handle it)

            # Step 3: Delete file from storage
            if file_path:
                try:
                    deleted = self.storage_service.delete_file(file_path)
                    if deleted:
                        logger.debug(f"Deleted face crop file: {file_path}")
                    else:
                        logger.warning(f"Face crop file not found: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete face crop file {file_path}: {e}")
                    # Continue with deletion

            # Step 4: Delete from DB
            self.db.delete(face)
            self.db.flush()  # Flush to ensure deletion is visible in this transaction
            logger.debug(f"Deleted face {face_id} from database")

            # Step 5: Update entity intelligence face_count
            self._decrement_face_count(entity_id)

            self.db.commit()
            logger.info(f"Successfully deleted face {face_id}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to delete face {face_id}: {e}")
            raise

    def delete_faces_for_entity(self, entity_id: int) -> int:
        """Delete all faces for an entity (DB + Vector + Files).

        This is used during entity deletion to clean up all associated faces.

        Args:
            entity_id: Entity ID

        Returns:
            Number of faces deleted
        """
        try:
            # Get all faces for this entity
            faces = self.db.query(Face).filter(Face.entity_id == entity_id).all()
            if not faces:
                logger.debug(f"No faces found for entity {entity_id}")
                return 0

            deleted_count = 0
            for face in faces:
                # Delete from vector store
                try:
                    self.face_store.delete_vector(face.id)
                    logger.debug(f"Deleted face {face.id} from vector store")
                except Exception as e:
                    logger.warning(f"Failed to delete face {face.id} from vector store: {e}")

                # Delete file from storage
                if face.file_path:
                    try:
                        self.storage_service.delete_file(face.file_path)
                        logger.debug(f"Deleted face crop file: {face.file_path}")
                    except Exception as e:
                        logger.warning(f"Failed to delete face crop file {face.file_path}: {e}")

                # Delete from DB
                self.db.delete(face)
                deleted_count += 1

            self.db.flush()  # Flush deletions
            logger.info(f"Deleted {deleted_count} faces for entity {entity_id}")
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to delete faces for entity {entity_id}: {e}")
            raise

    def _decrement_face_count(self, entity_id: int) -> None:
        """Decrement face_count in entity's intelligence_data.

        Args:
            entity_id: Entity ID
        """
        entity = self.db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            logger.warning(f"Entity {entity_id} not found for face_count update")
            return

        # Get current intelligence data
        intelligence_data = None
        if hasattr(entity, "intelligence_data") and entity.intelligence_data:
            try:
                intelligence_data = EntityIntelligenceData.model_validate(entity.intelligence_data)
            except Exception as e:
                logger.warning(f"Failed to parse intelligence_data for entity {entity_id}: {e}")
                intelligence_data = EntityIntelligenceData()
        else:
            intelligence_data = EntityIntelligenceData()

        # Decrement face_count
        if intelligence_data.face_count and intelligence_data.face_count > 0:
            intelligence_data.face_count -= 1
            logger.debug(
                f"Decremented face_count for entity {entity_id} "
                f"to {intelligence_data.face_count}"
            )
        else:
            intelligence_data.face_count = 0
            logger.warning(f"face_count was already 0 or None for entity {entity_id}")

        # Update entity
        entity.intelligence_data = intelligence_data.model_dump()
        self.db.flush()
