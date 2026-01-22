from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from cl_ml_tools.plugins.face_detection.schema import FaceDetectionOutput
from loguru import logger
from numpy.typing import NDArray
from pydantic import ValidationError

from store.common.models import Entity, Face, FaceMatch, ImageIntelligence, KnownPerson

from .vector_stores import QdrantVectorStore, StoreItem

if TYPE_CHECKING:
    from cl_client import ComputeClient
    from cl_client.models import JobResponse

    from .config import MInsightConfig
    from .job_service import JobSubmissionService


class JobCallbackHandler:
    """Handler for job completion callbacks."""

    compute_client: ComputeClient
    clip_store: QdrantVectorStore
    dino_store: QdrantVectorStore
    face_store: QdrantVectorStore

    def __init__(
        self,
        compute_client: ComputeClient,
        clip_store: QdrantVectorStore,
        dino_store: QdrantVectorStore,
        face_store: QdrantVectorStore,
        config: MInsightConfig,
        job_submission_service: JobSubmissionService | None = None,
    ) -> None:
        """Initialize callback handler.

        Args:
            compute_client: ComputeClient for file downloads
            clip_store: QdrantVectorStore for CLIP embedding storage
            dino_store: QdrantVectorStore for DINOv2 embedding storage
            face_store: QdrantVectorStore for Face embedding storage
            config: MInsight configuration
            job_submission_service: Service for submitting jobs (optional for initialization)
        """
        self.compute_client = compute_client
        self.clip_store = clip_store
        self.dino_store = dino_store
        self.face_store = face_store
        self.config = config
        self.job_submission_service: JobSubmissionService | None = (
            job_submission_service
        )

    @staticmethod
    def _now_timestamp() -> int:
        """Get current timestamp in milliseconds.

        Returns:
            Current timestamp in milliseconds since epoch
        """
        return int(datetime.now(UTC).timestamp() * 1000)

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

    def _get_face_storage_path(
        self, image_id: int, face_index: int, entity_create_date: int
    ) -> Path:
        """Get storage path for face image using original entity's creation date.

        Args:
            image_id: Image (Entity) ID
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

        # Create directory structure: {MEDIA_STORAGE_DIR}/faces/YYYY/MM/DD/
        base_dir = self.config.media_storage_dir
        dir_path = base_dir / "faces" / year / month / day
        dir_path.mkdir(parents=True, exist_ok=True)

        # Filename: {image_id}_face_{index}.png
        filename = f"{image_id}_face_{face_index}.png"

        return dir_path / filename

    async def handle_face_detection_complete(
        self, image_id: int, job: JobResponse
    ) -> None:
        """Handle face detection job completion.

        Downloads cropped faces, saves to files, and creates Face records in database.

        Args:
            image_id: Image (Entity) ID
            job: Job response from MQTT callback (minimal data, needs full fetch)
        """
        from store.common.database import SessionLocal

        db = SessionLocal()
        try:
            # Check if job failed
            if job.status == "failed":
                logger.error(
                    f"Face detection job {job.job_id} failed for image {image_id}: "
                    + f"{job.error_message}"
                )
                return

            # MQTT callbacks don't include task_output - fetch full job via HTTP
            full_job = await self.compute_client.get_job(job.job_id)
            if not full_job or full_job.status != "completed":
                logger.warning(
                    f"Job {job.job_id} not completed when fetching full details (status: {full_job.status if full_job else 'None'})"
                )
                return

            # Query Entity to get its create_date for organizing face files
            entity = db.query(Entity).filter(Entity.id == image_id).first()
            if not entity:
                logger.error(
                    f"Entity {image_id} not found for face detection job {job.job_id}"
                )
                return

            # Extract faces from task_output
            if not full_job.task_output or "faces" not in full_job.task_output:
                logger.warning(
                    f"No faces found in job {job.job_id} output for image {image_id}"
                )
                return

            try:
                task_output: FaceDetectionOutput = FaceDetectionOutput.model_validate(
                    full_job.task_output
                )
                faces_data = task_output.faces
            except ValidationError as e:
                logger.error(f"Invalid task_output format for job {job.job_id}: {e}")
                return

            # Phase 1: Download face images and create Face records
            saved_faces: list[tuple[int, Path]] = []  # (face_id, face_path)

            # Using storage_service for path resolution would be ideal here if available,
            # but _get_face_storage_path logic is specific.
            # Could move to common/models.py Face.get_file_path reverse logic?
            # For now keeping logic here as it implies creation logic.

            for index, face_data in enumerate(faces_data):
                try:
                    # Get storage path for face image using entity's create_date
                    face_path = self._get_face_storage_path(
                        image_id,
                        index,
                        entity.create_date
                        if entity.create_date
                        else entity.updated_date
                        if entity.updated_date
                        else 0,
                    )

                    # Download face image
                    await self._download_face_image(
                        job_id=job.job_id,
                        file_path=face_data.file_path,
                        dest=face_path,
                    )

                    # Get relative path from MEDIA_STORAGE_DIR
                    relative_path = face_path.relative_to(
                        self.config.media_storage_dir
                    )

                    # Generate deterministic face ID: image_id * 10000 + face_index
                    # This prevents duplicates if callback runs multiple times
                    face_id = image_id * 10000 + index

                    # Check if face already exists (upsert pattern)
                    existing_face = db.query(Face).filter(Face.id == face_id).first()

                    if existing_face:
                        # Update existing face
                        existing_face.bbox = face_data.bbox.model_dump_json()
                        existing_face.confidence = face_data.confidence
                        existing_face.landmarks = face_data.landmarks.model_dump_json()
                        existing_face.file_path = str(relative_path)
                        face = existing_face
                        logger.debug(
                            f"Updated existing face {face_id} for image {image_id}"
                        )
                    else:
                        # Create new face with explicit ID
                        face = Face(
                            id=face_id,
                            image_id=image_id,
                            bbox=face_data.bbox.model_dump_json(),
                            confidence=face_data.confidence,
                            landmarks=face_data.landmarks.model_dump_json(),
                            file_path=str(relative_path),
                            created_at=self._now_timestamp(),
                        )
                        db.add(face)
                        logger.debug(
                            f"Created new face {face_id} for image {image_id}"
                        )

                    db.flush()

                    saved_faces.append((face.id, face_path))

                    logger.debug(
                        f"Saved face {index} for image {image_id} "
                        + f"(confidence: {face_data.confidence:.2f})"
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to process face {index} from job {job.job_id} "
                        + f"for image {image_id}: {e}"
                    )
                    # Continue processing other faces

            # Commit all Face records BEFORE submitting jobs
            db.commit()
            logger.info(
                f"Successfully saved {len(saved_faces)} faces for image {image_id}"
            )

            # Phase 2: Submit face_embedding jobs (after commit to avoid locks)
            if self.job_submission_service:
                face_job_ids = []
                for face_id, face_path in saved_faces:
                    try:
                        # Capture face_id in closure
                        async def face_embedding_callback(
                            job: JobResponse, fid: int = face_id
                        ) -> None:
                            await self.handle_face_embedding_complete(
                                face_id=fid,
                                image_id=image_id,
                                job=job,
                            )
                            if self.job_submission_service:
                                self.job_submission_service.update_job_status(
                                    job.job_id, job.status, job.error_message
                                )

                        # Fetch the Face object to pass to submit_face_embedding
                        # We need to re-query or use the ID.
                        # JobSubmissionService.submit_face_embedding now expects 'face' object and 'entity version data'?
                        # Or maybe just IDs?
                        # Plan said: submit_face_embedding(face: Face, entity: EntityVersionData, ...)
                        # But here we are inside a callback where we have IDs.
                        # We must query the objects to pass them, or update JobSubmissionService to take IDs?
                        # I will assume JobSubmissionService will be updated to take Objects (per plan), so I need to query them.

                        f_obj = db.query(Face).filter(Face.id == face_id).first()

                        # We need EntityVersionData for entity.
                        # We have 'entity' ORM object. Convert to EntityVersionData Pydantic model?
                        # Or does JobSubmissionService take ORM objects?
                        # Plan said: "submit_face_embedding(face: Face, entity: EntityVersionData, ...)"
                        # Let's convert entity to EntityVersionData if possible.
                        # EntityVersionData is for VERSIONED data. Here we have live Entity.
                        # It should be compatible if we look at fields.

                        # Construct minimal EVD or query version?
                        # EntityVersionData expects transaction_id which Entity doesn't have directly (it has versions rel).
                        # Taking a shortcut: If JobSubmissionService only needs path, we can pass what is needed.
                        # But plan dictates signature change.
                        # I will UPDATE JobSubmissionService to be flexible or take Entity/Face objects.

                        if f_obj:
                            # Create a temporary/partial EVD or we assume JobSubmissionService handles it.
                            # For now, I will update JobSubmissionService to take Face object and maybe Entity object or EVD.

                            # Actually, inside callback we might not have the version data handy easily without querying.
                            # For simplicity, I will stick to IDs and path in this call if JobSubmissionService supports it,
                            # OR I'll query what I need.

                            pass

                            # WAIT. In the plan I said:
                            # submit_face_embedding(face: Face, entity: EntityVersionData, on_complete_callback)

                            # Here in callback we have the Entity object.
                            # Does it matter if it is Entity or EntityVersionData?
                            # Primarily for get_file_path() I presume.

                            # Let's update JobSubmissionService to accept Face and Entity (or EVD).
                            # I'll pass the ORM objects if compatible or update JobSubmissionService to take Union.

                            # For now, I'll call it with arguments I have.
                            # submit_face_embedding method signature update is pending in next step.
                            # I will invoke it assuming I pass the objects.

                            job_id = await self.job_submission_service.submit_face_embedding(
                                face=f_obj,
                                entity=entity, # Passing ORM entity
                                on_complete_callback=face_embedding_callback,
                            )
                            if job_id:
                                face_job_ids.append(job_id)

                    except Exception as e:
                        logger.error(
                            f"Failed to submit face_embedding job for face {face_id}: {e}"
                        )

                # Update ImageIntelligence with job IDs
                if face_job_ids:
                    try:
                        intelligence = db.query(ImageIntelligence).filter(ImageIntelligence.image_id == image_id).first()
                        if intelligence:
                            current_ids = intelligence.face_embedding_job_ids or []
                            # Use casting or direct assignment
                            # SQLAlchemy might need a copy to detect change for JSON type
                            new_ids = list(current_ids) + face_job_ids
                            intelligence.face_embedding_job_ids = new_ids
                            db.commit()
                            logger.info(f"Updated ImageIntelligence for {image_id} with {len(face_job_ids)} face embedding jobs")
                    except Exception as e:
                        logger.error(f"Failed to update ImageIntelligence with face job IDs for {image_id}: {e}")
        except Exception as e:
            logger.error(
                f"Failed to handle face detection completion for image {image_id}: {e}"
            )
            db.rollback()
        finally:
            db.close()

    async def handle_clip_embedding_complete(
        self, image_id: int, job: JobResponse
    ) -> None:
        """Handle CLIP embedding job completion.

        Extracts embedding and stores in Qdrant with image_id as point_id.

        Args:
            image_id: Image (Entity) ID (used as Qdrant point_id)
            job: Job response from MQTT callback (minimal data, needs full fetch)
        """
        try:
            # Check if job failed
            if job.status == "failed":
                logger.error(
                    f"CLIP embedding job {job.job_id} failed for image {image_id}: "
                    + f"{job.error_message}"
                )
                return

            # MQTT callbacks don't include task_output - fetch full job via HTTP
            full_job = await self.compute_client.get_job(job.job_id)
            if not full_job or full_job.status != "completed":
                logger.warning(
                    f"Job {job.job_id} not completed when fetching full details (status: {full_job.status if full_job else 'None'})"
                )
                return

            # Download embedding file from job output
            # The embedding is stored in a .npy file (numpy JSON format)
            if not full_job.params or "output_path" not in full_job.params:
                logger.error(f"No output_path found in job {job.job_id} params")
                return

            output_path = cast(str, full_job.params["output_path"])

            # Download embedding file to temporary location
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".npy", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            try:
                await self.compute_client.download_job_file(
                    job_id=job.job_id,
                    file_path=output_path,
                    dest=tmp_path,
                )

                # Load .npy file (numpy binary format)
                import numpy as np

                embedding: NDArray[np.float32] = cast(
                    NDArray[np.float32], np.load(tmp_path)
                )

                # Validate embedding dimension
                if embedding.shape[0] != 512:
                    logger.error(
                        f"Invalid embedding dimension for image {image_id}: expected 512, got {embedding.shape[0]}"
                    )
                    return

            finally:
                # Cleanup temporary file
                if tmp_path.exists():
                    tmp_path.unlink()

            # Store in Qdrant with image_id as point_id
            _ = self.clip_store.add_vector(
                StoreItem(
                    id=image_id,
                    embedding=embedding,
                    payload={"image_id": image_id},
                )
            )

            logger.info(
                f"Successfully stored CLIP embedding for image {image_id} in Qdrant"
            )

        except Exception as e:
            logger.error(
                f"Failed to handle CLIP embedding completion for image {image_id}: {e}"
            )

    async def handle_dino_embedding_complete(
        self, image_id: int, job: JobResponse
    ) -> None:
        """Handle DINOv2 embedding job completion.

        Extracts embedding and stores in Qdrant (DINO collection) with image_id as point_id.

        Args:
            image_id: Image (Entity) ID (used as Qdrant point_id)
            job: Job response from MQTT callback (minimal data, needs full fetch)
        """
        try:
            # Check if job failed
            if job.status == "failed":
                logger.error(
                    f"DINO embedding job {job.job_id} failed for image {image_id}: "
                    + f"{job.error_message}"
                )
                return

            # MQTT callbacks don't include task_output - fetch full job via HTTP
            full_job = await self.compute_client.get_job(job.job_id)
            if not full_job or full_job.status != "completed":
                logger.warning(
                    f"Job {job.job_id} not completed when fetching full details (status: {full_job.status if full_job else 'None'})"
                )
                return

            # Download embedding file from job output
            if not full_job.params or "output_path" not in full_job.params:
                logger.error(f"No output_path found in job {job.job_id} params")
                return

            output_path = cast(str, full_job.params["output_path"])

            # Download embedding file to temporary location
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".npy", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            try:
                await self.compute_client.download_job_file(
                    job_id=job.job_id,
                    file_path=output_path,
                    dest=tmp_path,
                )

                # Load .npy file
                import numpy as np

                embedding: NDArray[np.float32] = cast(
                    NDArray[np.float32], np.load(tmp_path)
                )

                # Validate embedding dimension (DINOv2-S is 384)
                if embedding.shape[0] != 384:
                    logger.error(
                        f"Invalid embedding dimension for image {image_id}: expected 384, got {embedding.shape[0]}"
                    )
                    return

            finally:
                # Cleanup temporary file
                if tmp_path.exists():
                    tmp_path.unlink()

            # Store in Qdrant (DINO collection) with image_id as point_id
            _ = self.dino_store.add_vector(
                StoreItem(
                    id=image_id,
                    embedding=embedding,
                    payload={"image_id": image_id},
                )
            )

            logger.info(
                f"Successfully stored DINO embedding for image {image_id} in Qdrant"
            )

        except Exception as e:
            logger.error(
                f"Failed to handle DINO embedding completion for image {image_id}: {e}"
            )

    async def handle_face_embedding_complete(
        self, face_id: int, image_id: int, job: JobResponse
    ) -> None:
        """Handle face embedding job completion.

        1. Extract embedding from job output
        2. Search face store for similar faces
        3. If match found: Link face to existing KnownPerson and record all matches
        4. If no match: Create new KnownPerson and add face to store

        Args:
            face_id: Face record ID
            image_id: Original image Entity ID (for reference/logging)
            job: Job response from MQTT callback (minimal data, needs full fetch)
        """
        from store.common.database import SessionLocal

        db = SessionLocal()
        try:
            # Check if job failed
            if job.status == "failed":
                logger.error(
                    f"Face embedding job {job.job_id} failed for face {face_id}: {job.error_message}"
                )
                return

            # MQTT callbacks don't include task_output - fetch full job via HTTP
            full_job = await self.compute_client.get_job(job.job_id)
            if not full_job or full_job.status != "completed":
                logger.warning(
                    f"Job {job.job_id} not completed when fetching full details (status: {full_job.status if full_job else 'None'})"
                )
                return

            # Download embedding file from job output
            # The embedding is stored in a .npy file (numpy JSON format)
            if not full_job.params or "output_path" not in full_job.params:
                logger.error(f"No output_path found in job {job.job_id} params")
                return

            output_path = cast(str, full_job.params["output_path"])

            # Download embedding file to temporary location
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".npy", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            try:
                await self.compute_client.download_job_file(
                    job_id=job.job_id,
                    file_path=output_path,
                    dest=tmp_path,
                )

                # Load .npy file (numpy binary format)
                import numpy as np

                embedding: NDArray[np.float32] = cast(
                    NDArray[np.float32], np.load(tmp_path)
                )

                # Validate embedding dimension
                if embedding.shape[0] != self.config.face_vector_size:
                    logger.error(
                        f"Invalid embedding dimension for face {face_id}: expected {self.config.face_vector_size}, got {embedding.shape[0]}"
                    )
                    return

            finally:
                # Cleanup temporary file
                if tmp_path.exists():
                    tmp_path.unlink()

            # Search face store for similar faces (get multiple matches for analysis)
            from .vector_stores import SearchPreferences

            similar_faces = self.face_store.search(
                query_vector=embedding,
                limit=10,  # Get up to 10 matches
                search_options=SearchPreferences(
                    score_threshold=self.config.face_embedding_threshold
                ),
            )

            # Get Face record
            face = db.query(Face).filter(Face.id == face_id).first()
            if not face:
                logger.error(f"Face {face_id} not found in database")
                return

            # Find the best valid match from similar faces
            valid_best_face = None
            if similar_faces:
                # Retry loop to handle concurrent processing of faces for the same person
                # If we find matches but none have a known_person_id, wait slightly and re-check
                max_retries = 3
                for retry in range(max_retries):
                    for match in similar_faces:
                        candidate_face = (
                            db.query(Face).filter(Face.id == match.id).first()
                        )
                        if candidate_face:
                            valid_best_face = candidate_face
                            # Link to this face's KnownPerson if it has one
                            if valid_best_face.known_person_id:
                                face.known_person_id = valid_best_face.known_person_id
                                logger.info(
                                    f"Linked face {face_id} to known person {valid_best_face.known_person_id} "
                                    + f"(match: {match.id}, score: {match.score:.3f})"
                                )
                                break

                    if face.known_person_id or not similar_faces:
                        break

                    if retry < max_retries - 1:
                        logger.debug(
                            f"Matches found for face {face_id} but no known_person_id assigned yet. Retrying {retry+1}/{max_retries}..."
                        )
                        await asyncio.sleep(1.0)
                        db.refresh(face)  # Ensure we have latest data

            # Record ALL matches in FaceMatch table
            if similar_faces:
                for match in similar_faces:
                    # Verify matched face exists in DB to prevent FK violation (stale vector store data)
                    matched_face_in_db = db.query(Face).filter(Face.id == match.id).first()
                    if not matched_face_in_db:
                        logger.warning(
                            f"Matched face {match.id} from vector store not found in DB. Skipping match record."
                        )
                        continue

                    face_match = FaceMatch(
                        face_id=face_id,
                        matched_face_id=match.id,
                        similarity_score=match.score,
                        created_at=self._now_timestamp(),
                    )
                    db.add(face_match)
                    logger.debug(
                        f"Recorded match: face {face_id} <-> face {match.id} (score: {match.score:.3f})"
                    )

            # If no valid similar face found (or no similar faces at all), create new KnownPerson
            if not valid_best_face or not face.known_person_id:
                # No match - create new KnownPerson
                if not face.known_person_id:
                    known_person = KnownPerson(
                        created_at=self._now_timestamp(),
                        updated_at=self._now_timestamp(),
                    )
                    db.add(known_person)
                    db.flush()  # Get ID

                    face.known_person_id = known_person.id
                    logger.info(
                        f"Created new known person {known_person.id} for face {face_id}"
                    )

            # Add face embedding to face store
            import numpy as np

            _ = self.face_store.add_vector(
                StoreItem(
                    id=face_id,
                    embedding=np.array(embedding, dtype=np.float32),
                    payload={
                        "face_id": face_id,
                        "image_id": image_id,
                        "known_person_id": face.known_person_id,
                    },
                )
            )

            db.commit()
            logger.info(f"Successfully processed face embedding for face {face_id}")

        except Exception as e:
            logger.error(
                f"Failed to handle face embedding completion for face {face_id}: {e}"
            )
            db.rollback()
        finally:
            db.close()
