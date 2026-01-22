from __future__ import annotations

import logging

from cl_ml_tools.plugins.face_detection.schema import BBox, FaceLandmarks
from sqlalchemy.orm import Session

from store.common.models import EntityJob, Face, FaceMatch, KnownPerson
from store.store.config import StoreConfig

from . import schemas
from .vector_stores import SearchPreferences, get_clip_store, get_dino_store, get_face_store

logger = logging.getLogger(__name__)


class ResourceNotFoundError(Exception):
    """Raised when a requested resource is not found."""
    pass



class IntelligenceRetrieveService:
    """Service layer for intelligence/ML retrieval operations (DB and Qdrant).

    This service depends only on the database and StoreConfig (which contains Qdrant settings),
    avoiding the need for ML Compute/Auth credentials in the Store process.
    """

    def __init__(self, db: Session, config: StoreConfig):
        """Initialize the intelligence retrieval service."""
        self.db = db
        self.config = config

        # Initialize stores from StoreConfig
        self.qdrant_store = get_clip_store(
            url=config.qdrant_url,
            collection_name=config.qdrant_collection,
        )
        self.face_store = get_face_store(
            url=config.qdrant_url,
            collection_name=config.face_collection,
            vector_size=getattr(config, "face_vector_size", 512),
        )
        self.dino_store = get_dino_store(
            url=config.qdrant_url,
            collection_name=config.dino_collection,
        )

    def _get_entity_or_raise(self, entity_id: int) -> None:
        """Check if entity exists, raise exception if not."""
        from store.common.models import Entity
        exists = self.db.query(Entity.id).filter(Entity.id == entity_id).scalar()
        if not exists:
            raise ResourceNotFoundError("Entity not found")

    def _get_face_or_raise(self, face_id: int) -> None:
        """Check if face exists, raise exception if not."""
        from store.common.models import Face
        exists = self.db.query(Face.id).filter(Face.id == face_id).scalar()
        if not exists:
            raise ResourceNotFoundError("Face not found")


    def get_entity_faces(self, entity_id: int) -> list[schemas.FaceResponse]:
        """Get all faces detected in an entity."""
        self._get_entity_or_raise(entity_id)
        faces = self.db.query(Face).filter(Face.image_id == entity_id).all()

        results: list[schemas.FaceResponse] = []
        for face in faces:
            results.append(
                schemas.FaceResponse(
                    id=face.id,
                    image_id=face.image_id,
                    bbox=BBox.model_validate_json(face.bbox),
                    confidence=face.confidence,
                    landmarks=FaceLandmarks.model_validate_json(face.landmarks),
                    file_path=face.file_path,
                    created_at=face.created_at,
                    known_person_id=face.known_person_id,
                )
            )
        return results

    def get_entity_jobs(self, entity_id: int) -> list[schemas.EntityJobResponse]:
        """Get all jobs for an entity."""
        self._get_entity_or_raise(entity_id)
        jobs = self.db.query(EntityJob).filter(EntityJob.image_id == entity_id).all()

        results: list[schemas.EntityJobResponse] = []
        for job in jobs:
            results.append(
                schemas.EntityJobResponse(
                    id=job.id,
                    image_id=job.image_id,
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
    ) -> list[schemas.SimilarImageResult]:
        """Search for similar images using CLIP embeddings."""
        self._get_entity_or_raise(entity_id)

        # Get the query embedding from Qdrant
        query_point = self.qdrant_store.get_vector(entity_id)
        if not query_point:
            logger.warning(f"No CLIP embedding found for entity {entity_id}")
            return []

        query_vector = query_point.embedding

        # Search for similar images
        results = self.qdrant_store.search(
            query_vector=query_vector,
            limit=limit + 1,  # +1 because query itself will be in results
            search_options=SearchPreferences(
                with_payload=True,
                score_threshold=score_threshold,
            ),
        )

        # Filter out the query entity itself and convert to Pydantic
        filtered_results: list[schemas.SimilarImageResult] = []
        for result in results:
            if result.id != entity_id:
                filtered_results.append(
                    schemas.SimilarImageResult(
                        image_id=int(result.id),  # type: ignore[arg-type]
                        score=float(result.score),
                        entity=None,  # Will be populated by route handler if requested
                    )
                )

        return filtered_results[:limit]

    def get_known_person(self, person_id: int) -> schemas.KnownPersonResponse | None:
        """Get known person details."""
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

    def search_similar_images_dino(
        self, entity_id: int, limit: int = 10, threshold: float | None = None
    ) -> schemas.SimilarImagesDinoResponse:
        """Search for similar images using DINOv2 embeddings."""
        self._get_entity_or_raise(entity_id)

        # Get embedding for query image
        item = self.dino_store.get_vector(entity_id)
        if not item:
            return schemas.SimilarImagesDinoResponse(
                query_image_id=entity_id,
                results=[],
            )

        # Search
        search_results = self.dino_store.search(
            query_vector=item.embedding,
            limit=limit + 1,  # +1 to account for the query image itself
            search_options=SearchPreferences(
                score_threshold=threshold if threshold is not None else 0.7  # Default DINO threshold
            ),
        )

        results: list[schemas.SimilarImageDinoResult] = []
        for result in search_results:
            if result.id == entity_id:
                continue

            results.append(
                schemas.SimilarImageDinoResult(
                    image_id=int(result.id),
                    score=result.score,
                )
            )

        return schemas.SimilarImagesDinoResponse(
            query_image_id=entity_id,
            results=results,
        )

    def get_all_known_persons(self) -> list[schemas.KnownPersonResponse]:
        """Get all known persons."""
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

    def get_known_person_faces(self, person_id: int) -> list[schemas.FaceResponse]:
        """Get all faces for a known person."""
        # Check if person exists
        person_exists = self.db.query(KnownPerson.id).filter(KnownPerson.id == person_id).scalar()
        if not person_exists:
            raise ResourceNotFoundError("Known person not found")

        faces = self.db.query(Face).filter(Face.known_person_id == person_id).all()

        results: list[schemas.FaceResponse] = []
        for face in faces:
            results.append(
                schemas.FaceResponse(
                    id=face.id,
                    image_id=face.image_id,
                    bbox=BBox.model_validate_json(face.bbox),
                    confidence=face.confidence,
                    landmarks=FaceLandmarks.model_validate_json(face.landmarks),
                    file_path=face.file_path,
                    created_at=face.created_at,
                    known_person_id=face.known_person_id,
                )
            )

        return results

    def get_face_matches(self, face_id: int) -> list[schemas.FaceMatchResult]:
        """Get all match records for a face."""
        self._get_face_or_raise(face_id)
        matches = self.db.query(FaceMatch).filter(FaceMatch.face_id == face_id).all()

        results: list[schemas.FaceMatchResult] = []
        for match in matches:
            # Optionally load matched face details
            matched_face = self.db.query(Face).filter(Face.id == match.matched_face_id).first()
            matched_face_response = None
            if matched_face:
                matched_face_response = schemas.FaceResponse(
                    id=matched_face.id,
                    image_id=matched_face.image_id,
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

    def update_known_person_name(
        self, person_id: int, name: str
    ) -> schemas.KnownPersonResponse | None:
        """Update known person name."""
        person = self.db.query(KnownPerson).filter(KnownPerson.id == person_id).first()
        if not person:
            return None

        person.name = name
        person.updated_at = self._now_timestamp()

        self.db.commit()
        self.db.refresh(person)

        return self.get_known_person(person_id)

    def _now_timestamp(self) -> int:
        """Return current UTC timestamp in milliseconds."""
        from datetime import UTC, datetime

        return int(datetime.now(UTC).timestamp() * 1000)

    def search_similar_faces_by_id(
        self, face_id: int, limit: int = 5, threshold: float = 0.7
    ) -> list[schemas.SimilarFacesResult]:
        """Search for similar faces using face store."""
        self._get_face_or_raise(face_id)

        # Get the query embedding from face store
        query_points = self.face_store.get_vector(face_id)
        if not query_points:
            logger.warning(f"No embedding found for face {face_id}")
            return []

        # Search for similar faces
        results = self.face_store.search(
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
                        image_id=face.image_id,
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


    def get_face_embedding_buffer(self, face_id: int):
        """Get face embedding as a numpy buffer.
        
        Args:
            face_id: ID of the face
            
        Returns:
            BytesIO buffer containing the .npy array
            
        Raises:
            ResourceNotFoundError: If face or embedding not found
        """
        import io

        import numpy as np

        self._get_face_or_raise(face_id)

        point = self.face_store.get_vector(id=face_id)
        if not point:
            raise ResourceNotFoundError("Face embedding not found in vector store")

        buffer = io.BytesIO()
        np.save(buffer, point.embedding)
        buffer.seek(0)
        return buffer

    def get_clip_embedding_buffer(self, entity_id: int):
        """Get CLIP embedding as a numpy buffer.
        
        Args:
            entity_id: ID of the entity
            
        Returns:
            BytesIO buffer containing the .npy array
            
        Raises:
            ResourceNotFoundError: If entity or embedding not found
        """
        import io

        import numpy as np

        self._get_entity_or_raise(entity_id)

        point = self.qdrant_store.get_vector(id=entity_id)
        if not point:
            raise ResourceNotFoundError("Entity embedding not found in vector store")

        buffer = io.BytesIO()
        np.save(buffer, point.embedding)
        buffer.seek(0)
        return buffer

    def get_dino_embedding_buffer(self, entity_id: int):
        """Get DINO embedding as a numpy buffer.
        
        Args:
            entity_id: ID of the entity
            
        Returns:
            BytesIO buffer containing the .npy array
            
        Raises:
            ResourceNotFoundError: If entity or embedding not found
        """
        import io

        import numpy as np

        self._get_entity_or_raise(entity_id)

        point = self.dino_store.get_vector(id=entity_id)
        if not point:
            raise ResourceNotFoundError("Entity embedding not found in vector store")

        buffer = io.BytesIO()
        np.save(buffer, point.embedding)
        buffer.seek(0)
        return buffer
