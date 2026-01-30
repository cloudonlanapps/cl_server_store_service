"""Service for data integrity auditing and orphan detection."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from store.db_service.db_internals import Entity, Face
from store.vectorstore_services.vector_stores import QdrantVectorStore

if TYPE_CHECKING:
    from ..common.storage import StorageService
    from ..broadcast_service.broadcaster import MInsightBroadcaster


class OrphanedFile(BaseModel):
    """Orphaned file in storage without DB entity."""

    file_path: str
    absolute_path: str


class OrphanedFace(BaseModel):
    """Orphaned Face record without valid entity."""

    face_id: int
    entity_id: int
    file_path: str | None


class OrphanedVector(BaseModel):
    """Orphaned vector in Qdrant without DB entity."""

    vector_id: int
    collection_name: str


class OrphanedMQTT(BaseModel):
    """Orphaned MQTT retained message without entity."""

    entity_id: int
    topic: str


class AuditReport(BaseModel):
    """Data integrity audit report."""

    orphaned_files: list[OrphanedFile] = Field(default_factory=list)
    orphaned_faces: list[OrphanedFace] = Field(default_factory=list)
    orphaned_vectors: list[OrphanedVector] = Field(default_factory=list)
    orphaned_mqtt: list[OrphanedMQTT] = Field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        """Check if report has any issues."""
        return bool(
            self.orphaned_files
            or self.orphaned_faces
            or self.orphaned_vectors
            or self.orphaned_mqtt
        )

    @property
    def total_issues(self) -> int:
        """Total number of issues found."""
        return (
            len(self.orphaned_files)
            + len(self.orphaned_faces)
            + len(self.orphaned_vectors)
            + len(self.orphaned_mqtt)
        )


class CleanupReport(BaseModel):
    """Orphan cleanup results."""

    files_deleted: int = 0
    faces_deleted: int = 0
    vectors_deleted: int = 0
    mqtt_cleared: int = 0

    @property
    def total_deleted(self) -> int:
        """Total items deleted."""
        return self.files_deleted + self.faces_deleted + self.vectors_deleted + self.mqtt_cleared


class AuditService:
    """Service for auditing data integrity and detecting orphaned resources."""

    def __init__(
        self,
        db: Session,
        storage_service: StorageService,
        clip_store: QdrantVectorStore | None = None,
        dino_store: QdrantVectorStore | None = None,
        face_store: QdrantVectorStore | None = None,
        broadcaster: MInsightBroadcaster | None = None,
    ):
        """Initialize the audit service.

        Args:
            db: SQLAlchemy database session
            storage_service: Storage service for file access
            clip_store: Qdrant vector store for CLIP embeddings (optional)
            dino_store: Qdrant vector store for DINO embeddings (optional)
            face_store: Qdrant vector store for face embeddings (optional)
            broadcaster: MQTT broadcaster (optional)
        """
        self.db: Session = db
        self.storage_service: StorageService = storage_service
        self.clip_store: QdrantVectorStore | None = clip_store
        self.dino_store: QdrantVectorStore | None = dino_store
        self.face_store: QdrantVectorStore | None = face_store
        self.broadcaster: MInsightBroadcaster | None = broadcaster

    def generate_report(self) -> AuditReport:
        """Generate comprehensive audit report of data integrity issues.

        This method performs readonly checks and does not modify any data.

        Returns:
            AuditReport with all detected issues
        """
        report = AuditReport()

        logger.info("Starting data integrity audit...")

        # Check 1: Orphaned files in storage
        report.orphaned_files = self._check_orphaned_files()
        logger.info(f"Found {len(report.orphaned_files)} orphaned files")

        # Check 2: Orphaned Face records
        report.orphaned_faces = self._check_orphaned_faces()
        logger.info(f"Found {len(report.orphaned_faces)} orphaned face records")

        # Check 3: Orphaned vectors in Qdrant
        report.orphaned_vectors = self._check_orphaned_vectors()
        logger.info(f"Found {len(report.orphaned_vectors)} orphaned vectors")

        # Check 4: Orphaned MQTT messages (if broadcaster available)
        if self.broadcaster:
            report.orphaned_mqtt = self._check_orphaned_mqtt()
            logger.info(f"Found {len(report.orphaned_mqtt)} orphaned MQTT messages")
        else:
            logger.debug("Skipping MQTT check (broadcaster not available)")

        logger.info(f"Audit complete: {report.total_issues} total issues found")
        return report

    def _check_orphaned_files(self) -> list[OrphanedFile]:
        """Scan storage directory for files without corresponding Entity records.

        Returns:
            List of orphaned files
        """
        orphaned = []
        media_dir = Path(self.storage_service.base_dir) / "store"

        if not media_dir.exists():
            logger.debug(f"Media directory {media_dir} does not exist")
            return orphaned

        # Get all entity file paths from DB
        entity_paths = set()
        entities = self.db.query(Entity.file_path).filter(Entity.file_path.isnot(None)).all()
        for (file_path,) in entities:
            if file_path:
                entity_paths.add(file_path)

        # Scan filesystem
        for file in media_dir.rglob("*"):
            if file.is_file():
                # Get relative path from base_dir
                try:
                    relative_path = str(file.relative_to(self.storage_service.base_dir))
                    if relative_path not in entity_paths:
                        orphaned.append(
                            OrphanedFile(
                                file_path=relative_path,
                                absolute_path=str(file),
                            )
                        )
                except ValueError:
                    # File is not relative to base_dir
                    continue

        return orphaned

    def _check_orphaned_faces(self) -> list[OrphanedFace]:
        """Check for Face records without valid Entity references.

        This can happen if:
        - Entity was hard-deleted without cascade (shouldn't happen with proper FK)
        - Data corruption

        Returns:
            List of orphaned face records
        """
        orphaned = []

        # Find faces whose entity_id doesn't exist in entities table
        faces = (
            self.db.query(Face)
            .outerjoin(Entity, Face.entity_id == Entity.id)
            .filter(Entity.id.is_(None))
            .all()
        )

        for face in faces:
            orphaned.append(
                OrphanedFace(
                    face_id=face.id,
                    entity_id=face.entity_id,
                    file_path=face.file_path,
                )
            )

        return orphaned

    def _check_orphaned_vectors(self) -> list[OrphanedVector]:
        """Check Qdrant collections for vectors without corresponding entities.

        Returns:
            List of orphaned vectors across all collections
        """
        orphaned = []

        # Get all valid entity IDs from DB
        valid_entity_ids = set()
        entities = self.db.query(Entity.id).all()
        for (entity_id,) in entities:
            valid_entity_ids.add(entity_id)

        # Get all valid face IDs from DB
        valid_face_ids = set()
        faces = self.db.query(Face.id).all()
        for (face_id,) in faces:
            valid_face_ids.add(face_id)

        # Check CLIP embeddings
        if self.clip_store:
            orphaned.extend(
                self._check_collection_orphans(
                    self.clip_store,
                    valid_entity_ids,
                    "clip_embeddings",
                )
            )

        # Check DINO embeddings
        if self.dino_store:
            orphaned.extend(
                self._check_collection_orphans(
                    self.dino_store,
                    valid_entity_ids,
                    "dino_embeddings",
                )
            )

        # Check Face embeddings (use face IDs, not entity IDs)
        if self.face_store:
            orphaned.extend(
                self._check_collection_orphans(
                    self.face_store,
                    valid_face_ids,
                    "face_embeddings",
                )
            )

        return orphaned

    def _check_collection_orphans(
        self,
        store: QdrantVectorStore,
        valid_ids: set[int],
        collection_name: str,
    ) -> list[OrphanedVector]:
        """Check a single Qdrant collection for orphaned vectors.

        Args:
            store: QdrantVectorStore instance
            valid_ids: Set of valid IDs from DB
            collection_name: Name of collection for reporting

        Returns:
            List of orphaned vectors in this collection
        """
        orphaned = []

        try:
            # Scroll through all points in collection
            # Note: This could be memory-intensive for large collections
            # Consider batching for production use
            scroll_result = store.client.scroll(
                collection_name=store.collection_name,
                limit=10000,  # Adjust based on expected collection size
                with_payload=False,
                with_vectors=False,
            )

            points = scroll_result[0] if scroll_result else []

            for point in points:
                point_id = int(point.id)  # type: ignore[arg-type]
                if point_id not in valid_ids:
                    orphaned.append(
                        OrphanedVector(
                            vector_id=point_id,
                            collection_name=collection_name,
                        )
                    )

        except Exception as e:
            logger.warning(f"Failed to check collection {collection_name}: {e}")

        return orphaned

    def _check_orphaned_mqtt(self) -> list[OrphanedMQTT]:
        """Check for retained MQTT messages for non-existent entities.

        Note: This is a placeholder implementation as we don't have direct
        access to MQTT broker's retained messages. In practice, this would
        require either:
        1. Tracking published topics in DB/memory
        2. Querying MQTT broker's admin API
        3. Subscribing to wildcard topics

        Returns:
            List of orphaned MQTT messages (currently empty)
        """
        orphaned = []

        # TODO: Implement MQTT retained message scanning
        # This would require broker-specific APIs or tracking
        logger.debug("MQTT orphan check not yet implemented")

        return orphaned
