from __future__ import annotations
import logging
from sqlalchemy.orm import Session
from cl_ml_tools.plugins.face_detection.schema import BBox, FaceLandmarks
from ..store.config import StoreConfig
from .logic.job_service import JobSubmissionService
from .logic.job_callbacks import JobCallbackHandler
from .logic.qdrant_singleton import get_qdrant_store
from .logic.compute_singleton import get_compute_client, get_pysdk_config
from .logic.face_store_singleton import get_face_store
from ..common import models, schemas
from ..common.schemas import (
    FaceResponse,
    EntityJobResponse,
    SimilarImageResult,
    KnownPersonResponse,
    FaceMatchResult,
    SimilarFacesResult,
)
from cl_client.models import JobResponse
from .logic.qdrant_image_store import SearchPreferences

logger = logging.getLogger(__name__)

class MInsightEmbeddingService:
    """Service layer for intelligence/ML operations."""

    def __init__(self, db: Session, config: StoreConfig):
        """Initialize the intelligence service."""
        self.db = db
        self.config = config
        # We assume file_storage is needed if we are triggering jobs
        from ..store.entity_storage import EntityStorageService
        self.file_storage = EntityStorageService(str(config.media_storage_dir))

    def _now_timestamp(self) -> int:
        """Return current UTC timestamp in milliseconds."""
        from datetime import UTC, datetime
        return int(datetime.now(UTC).timestamp() * 1000)

    async def trigger_async_jobs(self, entity: models.Entity) -> dict[str, str | None]:
        """Trigger face detection and CLIP embedding jobs for an entity."""
        # Get absolute file path
        if not entity.file_path:
            logger.warning(f"Entity {entity.id} has no file_path")
            return {"face_detection_job": None, "clip_embedding_job": None}

        absolute_path = self.file_storage.get_absolute_path(entity.file_path)
        if not absolute_path.exists():
            logger.warning(f"File not found for entity {entity.id}: {absolute_path}")
            return {"face_detection_job": None, "clip_embedding_job": None}

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

    def get_entity_faces(self, entity_id: int) -> list[FaceResponse]:
        """Get all faces detected in an entity."""
        faces = self.db.query(models.Face).filter(models.Face.entity_id == entity_id).all()

        results: list[FaceResponse] = []
        for face in faces:
            results.append(
                FaceResponse(
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
        """Get all jobs for an entity."""
        jobs = self.db.query(models.EntityJob).filter(models.EntityJob.entity_id == entity_id).all()

        results: list[EntityJobResponse] = []
        for job in jobs:
            results.append(
                EntityJobResponse(
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
        """Search for similar images using CLIP embeddings."""
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
                    SimilarImageResult(
                        entity_id=int(result.id),  # type: ignore[arg-type]
                        score=float(result.score),
                        entity=None,  # Will be populated by route handler if requested
                    )
                )

        return filtered_results[:limit]

    def get_known_person(self, person_id: int) -> KnownPersonResponse | None:
        """Get known person details."""
        person = self.db.query(models.KnownPerson).filter(models.KnownPerson.id == person_id).first()
        if not person:
            return None

        # Count faces for this person
        face_count = self.db.query(models.Face).filter(models.Face.known_person_id == person_id).count()

        return KnownPersonResponse(
            id=person.id,
            name=person.name,
            created_at=person.created_at,
            updated_at=person.updated_at,
            face_count=face_count,
        )

    def get_all_known_persons(self) -> list[KnownPersonResponse]:
        """Get all known persons."""
        persons = self.db.query(models.KnownPerson).all()

        results: list[KnownPersonResponse] = []
        for person in persons:
            # Count faces for this person
            face_count = self.db.query(models.Face).filter(models.Face.known_person_id == person.id).count()

            results.append(
                KnownPersonResponse(
                    id=person.id,
                    name=person.name,
                    created_at=person.created_at,
                    updated_at=person.updated_at,
                    face_count=face_count,
                )
            )

        return results

    def get_known_person_faces(self, person_id: int) -> list[FaceResponse]:
        """Get all faces for a known person."""
        faces = self.db.query(models.Face).filter(models.Face.known_person_id == person_id).all()

        results: list[FaceResponse] = []
        for face in faces:
            results.append(
                FaceResponse(
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
        """Update known person name."""
        person = self.db.query(models.KnownPerson).filter(models.KnownPerson.id == person_id).first()
        if not person:
            return None

        person.name = name
        person.updated_at = self._now_timestamp()

        self.db.commit()
        self.db.refresh(person)

        return self.get_known_person(person_id)

    def get_face_matches(self, face_id: int) -> list[FaceMatchResult]:
        """Get all match records for a face."""
        matches = self.db.query(models.FaceMatch).filter(models.FaceMatch.face_id == face_id).all()

        results: list[FaceMatchResult] = []
        for match in matches:
            # Optionally load matched face details
            matched_face = self.db.query(models.Face).filter(models.Face.id == match.matched_face_id).first()
            matched_face_response = None
            if matched_face:
                matched_face_response = FaceResponse(
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
                FaceMatchResult(
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
        """Search for similar faces using face store."""
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
        filtered_results: list[SimilarFacesResult] = []
        for result in results:
            if result.id != face_id:
                # Optionally load face details
                face = self.db.query(models.Face).filter(models.Face.id == result.id).first()
                face_response = None
                if face:
                    face_response = FaceResponse(
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
                    SimilarFacesResult(
                        face_id=int(result.id),  # type: ignore[arg-type]
                        score=float(result.score),
                        known_person_id=(
                            result.payload.get("known_person_id") if result.payload else None
                        ),
                        face=face_response,
                    )
                )

        return filtered_results[:limit]
