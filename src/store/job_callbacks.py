"""MQTT callback handlers for face detection and embedding jobs."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, cast

from cl_server_shared import Config
from sqlalchemy.orm import Session

from .models import Face

if TYPE_CHECKING:
    from cl_client import ComputeClient
    from cl_client.models import JobResponse

    from .job_service import JobSubmissionService
    from .pysdk_config import PySDKRuntimeConfig
    from .qdrant_image_store import QdrantImageStore

logger = logging.getLogger(__name__)


class JobCallbackHandler:
    """Handler for job completion callbacks."""

    db: Session
    compute_client: ComputeClient
    qdrant_store: QdrantImageStore

    def __init__(
        self,
        db: Session,
        compute_client: ComputeClient,
        qdrant_store: QdrantImageStore,
        job_submission_service: JobSubmissionService | None = None,
        pysdk_config: PySDKRuntimeConfig | None = None,
    ) -> None:
        """Initialize callback handler.

        Args:
            db: Database session
            compute_client: ComputeClient for file downloads
            qdrant_store: QdrantImageStore for embedding storage
            job_submission_service: Service for submitting jobs (optional for initialization)
            pysdk_config: PySDK runtime configuration (optional for initialization)
        """
        self.db = db
        self.compute_client = compute_client
        self.qdrant_store = qdrant_store
        self.job_submission_service = job_submission_service
        self.pysdk_config = pysdk_config

    @staticmethod
    def _now_timestamp() -> int:
        """Get current timestamp in milliseconds.

        Returns:
            Current timestamp in milliseconds since epoch
        """
        return int(datetime.now(UTC).timestamp() * 1000)

    @staticmethod
    def _convert_bbox_to_list(bbox_dict: dict[str, float]) -> list[float]:
        """Convert bbox dict to list format.

        Args:
            bbox_dict: Bbox as dict with x1, y1, x2, y2 keys

        Returns:
            Bbox as list [x1, y1, x2, y2]
        """
        return [
            bbox_dict["x1"],
            bbox_dict["y1"],
            bbox_dict["x2"],
            bbox_dict["y2"],
        ]

    @staticmethod
    def _convert_landmarks_to_list(landmarks_dict: dict[str, list[float]]) -> list[list[float]]:
        """Convert landmarks dict to list format.

        Args:
            landmarks_dict: Landmarks as dict with keypoint names

        Returns:
            Landmarks as list of [x, y] coordinates
        """
        # Order: right_eye, left_eye, nose_tip, mouth_right, mouth_left
        keypoint_order = ["right_eye", "left_eye", "nose_tip", "mouth_right", "mouth_left"]
        return [landmarks_dict[key] for key in keypoint_order]

    async def _download_face_image(
        self, job_id: str, file_path: str, dest: Path
    ) -> None:
        """Download face image from job output.

        Args:
            job_id: Job ID
            file_path: Relative file path in job output
            dest: Destination path for downloaded file
        """
        await self.compute_client.download_job_file(
            job_id=job_id,
            file_path=file_path,
            dest=dest,
        )

    def _get_face_storage_path(self, entity_id: int, face_index: int, entity_create_date: int) -> Path:
        """Get storage path for face image using original entity's creation date.

        Args:
            entity_id: Entity ID
            face_index: Face index (0, 1, 2, ...)
            entity_create_date: Entity creation timestamp in milliseconds

        Returns:
            Absolute path for face image storage
        """
        # Convert milliseconds timestamp to datetime
        dt = datetime.fromtimestamp(entity_create_date / 1000, UTC)
        year = dt.strftime("%Y")
        month = dt.strftime("%m")
        day = dt.strftime("%d")

        # Create directory structure: {MEDIA_STORAGE_DIR}/store/faces/YYYY/MM/DD/
        base_dir = Path(Config.MEDIA_STORAGE_DIR)
        dir_path = base_dir / "store" / "faces" / year / month / day
        dir_path.mkdir(parents=True, exist_ok=True)

        # Filename: {entity_id}_face_{index}.png
        filename = f"{entity_id}_face_{face_index}.png"

        return dir_path / filename

    def handle_face_detection_complete(self, entity_id: int, job: JobResponse) -> None:
        """Handle face detection job completion.

        Downloads cropped faces, saves to files, and creates Face records in database.

        Args:
            entity_id: Entity ID
            job: Job response from MQTT callback
        """
        try:
            # Check if job failed
            if job.status == "failed":
                logger.error(
                    f"Face detection job {job.job_id} failed for entity {entity_id}: " +
                    f"{job.error_message}"
                )
                return

            # Query Entity to get its create_date for organizing face files
            from .models import Entity
            entity = self.db.query(Entity).filter(Entity.id == entity_id).first()
            if not entity:
                logger.error(f"Entity {entity_id} not found for face detection job {job.job_id}")
                return

            # Extract faces from task_output
            if not job.task_output or "faces" not in job.task_output:
                logger.warning(
                    f"No faces found in job {job.job_id} output for entity {entity_id}"
                )
                return

            # Type-safe extraction of faces data
            task_output_raw = job.task_output
            if not isinstance(task_output_raw, dict):
                logger.error(f"Invalid task_output type for job {job.job_id}")
                return

            faces_raw = task_output_raw.get("faces")
            if not isinstance(faces_raw, list):
                logger.error(f"Invalid faces type in job {job.job_id} output")
                return

            faces_data = cast(list[dict[str, object]], faces_raw)
            logger.info(
                f"Processing {len(faces_data)} faces from job {job.job_id} " +
                f"for entity {entity_id}"
            )

            for index, face_data in enumerate(faces_data):
                try:
                    # Get storage path for face image using entity's create_date
                    face_path = self._get_face_storage_path(entity_id, index, entity.create_date)

                    # Download face image (async operation in sync context)
                    file_path_str = cast(str, face_data["file_path"])
                    asyncio.run(
                        self._download_face_image(
                            job_id=job.job_id,
                            file_path=file_path_str,
                            dest=face_path,
                        )
                    )

                    # Convert bbox and landmarks to JSON lists
                    bbox_dict = cast(dict[str, float], face_data["bbox"])
                    landmarks_dict = cast(dict[str, list[float]], face_data["landmarks"])

                    bbox_list = self._convert_bbox_to_list(bbox_dict)
                    landmarks_list = self._convert_landmarks_to_list(landmarks_dict)

                    # Get relative path from MEDIA_STORAGE_DIR
                    relative_path = face_path.relative_to(Path(Config.MEDIA_STORAGE_DIR))

                    # Create Face record
                    face = Face(
                        entity_id=entity_id,
                        bbox=json.dumps(bbox_list),
                        confidence=face_data["confidence"],
                        landmarks=json.dumps(landmarks_list),
                        file_path=str(relative_path),
                        created_at=self._now_timestamp(),
                    )

                    self.db.add(face)
                    self.db.flush()  # Flush to get face.id

                    logger.debug(
                        f"Saved face {index} for entity {entity_id} " +
                        f"(confidence: {face_data['confidence']:.2f})"  # type: ignore[index]
                    )

                    # Submit face_embedding job for this face
                    if self.job_submission_service:
                        face_embedding_callback = partial(
                            self.handle_face_embedding_complete,
                            face_id=face.id,
                            entity_id=entity_id,
                        )

                        asyncio.run(
                            self.job_submission_service.submit_face_embedding(
                                face_id=face.id,
                                entity_id=entity_id,
                                file_path=str(face_path),
                                on_complete_callback=face_embedding_callback,
                            )
                        )

                except Exception as e:
                    logger.error(
                        f"Failed to process face {index} from job {job.job_id} " +
                        f"for entity {entity_id}: {e}"
                    )
                    # Continue processing other faces

            # Commit all Face records
            self.db.commit()
            logger.info(
                f"Successfully saved {len(faces_data)} faces for entity {entity_id}"
            )

            # Cleanup: Delete successful job record
            if self.job_submission_service:
                self.job_submission_service.delete_job_record(job.job_id)

        except Exception as e:
            logger.error(
                f"Failed to handle face detection completion for entity {entity_id}: {e}"
            )
            self.db.rollback()

    def handle_clip_embedding_complete(self, entity_id: int, job: JobResponse) -> None:
        """Handle CLIP embedding job completion.

        Extracts embedding and stores in Qdrant with entity_id as point_id.

        Args:
            entity_id: Entity ID (used as Qdrant point_id)
            job: Job response from MQTT callback
        """
        try:
            # Check if job failed
            if job.status == "failed":
                logger.error(
                    f"CLIP embedding job {job.job_id} failed for entity {entity_id}: " +
                    f"{job.error_message}"
                )
                return

            # Extract embedding from task_output
            if not job.task_output or "embedding" not in job.task_output:
                logger.error(
                    f"No embedding found in job {job.job_id} output for entity {entity_id}"
                )
                return

            # Type-safe extraction of embedding
            task_output_raw = job.task_output
            if not isinstance(task_output_raw, dict):
                logger.error(f"Invalid task_output type for job {job.job_id}")
                return

            embedding_raw = task_output_raw.get("embedding")
            if not isinstance(embedding_raw, list):
                logger.error(f"Invalid embedding type in job {job.job_id} output")
                return

            embedding = cast(list[float], embedding_raw)

            # Validate embedding dimension
            if len(embedding) != 512:
                logger.error(
                    f"Invalid embedding dimension for entity {entity_id}: " +
                    f"expected 512, got {len(embedding)}"
                )
                return

            # Store in Qdrant with entity_id as point_id
            import numpy as np

            self.qdrant_store.add_vector(
                point_id=entity_id,
                vec_f32=np.array(embedding, dtype=np.float32),
                payload={"entity_id": entity_id},
            )

            logger.info(
                f"Successfully stored CLIP embedding for entity {entity_id} in Qdrant"
            )

            # Cleanup: Delete successful job record
            if self.job_submission_service:
                self.job_submission_service.delete_job_record(job.job_id)

        except Exception as e:
            logger.error(
                f"Failed to handle CLIP embedding completion for entity {entity_id}: {e}"
            )

    def handle_face_embedding_complete(self, face_id: int, entity_id: int, job: JobResponse) -> None:
        """Handle face embedding job completion.

        1. Extract embedding from job output
        2. Search face store for similar faces
        3. If match found: Link face to existing KnownPerson and record all matches
        4. If no match: Create new KnownPerson and add face to store

        Args:
            face_id: Face record ID
            entity_id: Original image Entity ID (for reference/logging)
            job: Job response from MQTT callback
        """
        try:
            # Check if job failed
            if job.status == "failed":
                logger.error(
                    f"Face embedding job {job.job_id} failed for face {face_id}: {job.error_message}"
                )
                return

            # Extract embedding from task_output
            if not job.task_output or "embedding" not in job.task_output:
                logger.error(f"No embedding found in job {job.job_id} output for face {face_id}")
                return

            # Type-safe extraction of embedding
            task_output_raw = job.task_output
            if not isinstance(task_output_raw, dict):
                logger.error(f"Invalid task_output type for job {job.job_id}")
                return

            embedding_raw = task_output_raw.get("embedding")
            if not isinstance(embedding_raw, list):
                logger.error(f"Invalid embedding type in job {job.job_id} output")
                return

            embedding = cast(list[float], embedding_raw)

            # Validate embedding dimension
            if len(embedding) != 512:
                logger.error(
                    f"Invalid embedding dimension for face {face_id}: expected 512, got {len(embedding)}"
                )
                return

            # Get pysdk_config for threshold
            if not self.pysdk_config:
                logger.error("PySDK config not available, cannot process face embedding")
                return

            # Get face store
            from .face_store_singleton import get_face_store

            face_store = get_face_store(self.pysdk_config)

            # Search face store for similar faces (get multiple matches for analysis)
            similar_faces = face_store.search(
                query_vector=embedding,
                limit=10,  # Get up to 10 matches
                score_threshold=self.pysdk_config.face_embedding_threshold,
            )

            # Get Face record
            from .models import FaceMatch, KnownPerson

            face = self.db.query(Face).filter(Face.id == face_id).first()
            if not face:
                logger.error(f"Face {face_id} not found in database")
                return

            if similar_faces:
                # Multiple matches found - link to BEST match, record ALL matches
                best_match = similar_faces[0]  # Highest similarity score
                best_face_id = best_match["id"]
                best_face = self.db.query(Face).filter(Face.id == best_face_id).first()

                if best_face and best_face.known_person_id:
                    # Link to best match's KnownPerson
                    face.known_person_id = best_face.known_person_id
                    logger.info(
                        f"Linked face {face_id} to known person {best_face.known_person_id} "
                        f"(score: {best_match['score']:.3f})"
                    )

                # Record ALL matches in FaceMatch table
                for match in similar_faces:
                    face_match = FaceMatch(
                        face_id=face_id,
                        matched_face_id=match["id"],
                        similarity_score=match["score"],
                        created_at=self._now_timestamp(),
                    )
                    self.db.add(face_match)
                    logger.debug(
                        f"Recorded match: face {face_id} <-> face {match['id']} (score: {match['score']:.3f})"
                    )
            else:
                # No match - create new KnownPerson
                known_person = KnownPerson(
                    created_at=self._now_timestamp(),
                    updated_at=self._now_timestamp(),
                )
                self.db.add(known_person)
                self.db.flush()  # Get ID

                face.known_person_id = known_person.id
                logger.info(f"Created new known person {known_person.id} for face {face_id}")

            # Add face embedding to face store
            import numpy as np

            face_store.add_vector(
                point_id=face_id,
                vec_f32=np.array(embedding, dtype=np.float32),
                payload={
                    "face_id": face_id,
                    "entity_id": entity_id,
                    "known_person_id": face.known_person_id,
                },
            )

            self.db.commit()
            logger.info(f"Successfully processed face embedding for face {face_id}")

            # Cleanup: Delete successful job record
            if self.job_submission_service:
                self.job_submission_service.delete_job_record(job.job_id)

        except Exception as e:
            logger.error(f"Failed to handle face embedding completion for face {face_id}: {e}")
            self.db.rollback()
