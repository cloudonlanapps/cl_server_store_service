from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import numpy as np
from cl_client import ComputeClient
from cl_client.models import JobResponse
from cl_ml_tools.plugins.face_detection.schema import FaceDetectionOutput
from cl_ml_tools.utils.profiling import timed
from loguru import logger
from numpy.typing import NDArray
from pydantic import ValidationError

from store.common import database
from store.common.database import with_retry
from store.common.models import Entity, Face, FaceMatch, ImageIntelligence, KnownPerson

from .config import MInsightConfig
from .job_service import JobSubmissionService
from .schemas import SearchPreferences, StoreItem
from .vector_stores import QdrantVectorStore


class JobCallbackHandler:
    """Handler for job completion callbacks."""

    compute_client: ComputeClient
    clip_store: QdrantVectorStore
    dino_store: QdrantVectorStore
    face_store: QdrantVectorStore
    config: MInsightConfig

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
        self.job_submission_service: JobSubmissionService | None = job_submission_service

    @staticmethod
    def _now_timestamp() -> int:
        """Get current timestamp in milliseconds.

        Returns:
            Current timestamp in milliseconds since epoch
        """
        return int(datetime.now(UTC).timestamp() * 1000)

    async def _download_face_image(self, job_id: str, file_path: str, dest: Path) -> None:
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
        self, entity_id: int, face_index: int, entity_create_date: int
    ) -> Path:
        """Get storage path for face image using original entity's creation date.

        Args:
            entity_id: Image (Entity) ID
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
        _ = dir_path.mkdir(parents=True, exist_ok=True)

        # Filename: {entity_id}_face_{index}.png
        filename = f"{entity_id}_face_{face_index}.png"

        return dir_path / filename

    @timed
    async def handle_face_detection_complete(self, entity_id: int, job: JobResponse) -> None:
        """Handle face detection job completion.

        Downloads cropped faces, saves to files, and creates Face records in database.

        Args:
            entity_id: Image (Entity) ID
            job: Job response from MQTT callback (minimal data, needs full fetch)
        """

        # Phase 1: Download face images and create/update Face records
        saved_faces: list[tuple[int, Path]] = []  # (face_id, face_path)

            # Get entity info needed for storage path (re-query in a small block)
            create_date = 0
            db_temp = database.SessionLocal()
            try:
                entity_temp = db_temp.query(Entity).filter(Entity.id == entity_id).first()
                if not entity_temp:
                    logger.error(f"Entity {entity_id} not found in database for job {job.job_id}")
                    return

                create_date = entity_temp.create_date or entity_temp.updated_date or 0
            finally:
                db_temp.close()

            # 2. Downloads (not needed to retry with DB logic)
            for index, face_data in enumerate(faces_data):
                face_path = self._get_face_storage_path(entity_id, index, create_date)
                await self._download_face_image(
                    job_id=job.job_id,
                    file_path=face_data.file_path,
                    dest=face_path,
                )

                # Deterministic face ID
                face_id = entity_id * 10000 + index
                saved_faces.append((face_id, face_path))

            # 3. DB Transaction (The part that needs retry)
            @with_retry(max_retries=10)
            def commit_faces_to_db():
                db = database.SessionLocal()
                try:
                    for index, face_data in enumerate(faces_data):
                        face_id, face_path = saved_faces[index]
                        relative_path = face_path.relative_to(self.config.media_storage_dir)

                        existing_face = db.query(Face).filter(Face.id == face_id).first()
                        if existing_face:
                            existing_face.bbox = face_data.bbox.model_dump_json()
                            existing_face.confidence = face_data.confidence
                            existing_face.landmarks = face_data.landmarks.model_dump_json()
                            existing_face.file_path = str(relative_path)
                        else:
                            face_obj = Face(
                                id=face_id,
                                entity_id=entity_id,
                                bbox=face_data.bbox.model_dump_json(),
                                confidence=face_data.confidence,
                                landmarks=face_data.landmarks.model_dump_json(),
                                file_path=str(relative_path),
                                created_at=self._now_timestamp(),
                            )
                            db.add(face_obj)
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
                finally:
                    db.close()

            commit_faces_to_db()
            logger.info(f"Successfully saved {len(saved_faces)} faces (ids: {[f[0] for f in saved_faces]}) for image {entity_id}")

            # Phase 2: Submit face_embedding jobs
            if self.job_submission_service:
                face_job_ids: list[str] = []
                for face_id, face_path in saved_faces:
                    try:

                        async def face_embedding_callback(
                            job: JobResponse, fid: int = face_id
                        ) -> None:
                            await self.handle_face_embedding_complete(
                                face_id=fid,
                                entity_id=entity_id,
                                job=job,
                            )
                            if self.job_submission_service:
                                self.job_submission_service.update_job_status(
                                    job.job_id, job.status, job.error_message
                                )

                        # Need to re-query objects to pass to submit_face_embedding
                        db_fetch = database.SessionLocal()
                        try:
                            f_obj = db_fetch.query(Face).filter(Face.id == face_id).first()
                            e_obj = db_fetch.query(Entity).filter(Entity.id == entity_id).first()
                            if f_obj and e_obj:
                                job_id = await self.job_submission_service.submit_face_embedding(
                                    face=f_obj,
                                    entity=e_obj,
                                    on_complete_callback=face_embedding_callback,
                                )
                                if job_id:
                                    face_job_ids.append(job_id)
                        finally:
                            db_fetch.close()

                    except Exception as e:
                        logger.error(f"Failed to submit face_embedding job for face {face_id}: {e}")

                # Update ImageIntelligence with job IDs
                if face_job_ids:

                    @with_retry(max_retries=10)
                    def update_intelligence():
                        db = database.SessionLocal()
                        try:
                            intelligence = (
                                db.query(ImageIntelligence)
                                .filter(ImageIntelligence.entity_id == entity_id)
                                .first()
                            )
                            if intelligence:
                                current_ids = intelligence.face_embedding_job_ids or []
                                intelligence.face_embedding_job_ids = (
                                    list(current_ids) + face_job_ids
                                )
                                db.commit()
                        except Exception:
                            db.rollback()
                            raise
                        finally:
                            db.close()

                    update_intelligence()
                    logger.info(
                        f"Updated ImageIntelligence for {entity_id} with {len(face_job_ids)} face embedding jobs"
                    )

            # Update job status in store database
            if self.job_submission_service:
                self.job_submission_service.update_job_status(
                    job.job_id, job.status, job.error_message
                )

        except Exception as e:
            logger.error(f"Failed to handle face detection completion for image {entity_id}: {e}")

    @timed
    async def handle_clip_embedding_complete(self, entity_id: int, job: JobResponse) -> None:
        """Handle CLIP embedding job completion.

        Extracts embedding and stores in Qdrant with entity_id as point_id.

        Args:
            entity_id: Image (Entity) ID (used as Qdrant point_id)
            job: Job response from MQTT callback (minimal data, needs full fetch)
        """
        try:
            # Check if job failed
            if job.status == "failed":
                logger.error(
                    f"CLIP embedding job {job.job_id} failed for image {entity_id}: "
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

            with tempfile.NamedTemporaryFile(suffix=".npy", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            try:
                await self.compute_client.download_job_file(
                    job_id=job.job_id,
                    file_path=output_path,
                    dest=tmp_path,
                )

                # Load .npy file (numpy binary format)

                embedding: NDArray[np.float32] = cast(NDArray[np.float32], np.load(tmp_path))

                # Validate embedding dimension
                if embedding.shape[0] != 512:
                    logger.error(
                        f"Invalid embedding dimension for image {entity_id}: expected 512, got {embedding.shape[0]}"
                    )
                    return

            finally:
                # Cleanup temporary file
                if tmp_path.exists():
                    tmp_path.unlink()

            # Store in Qdrant with entity_id as point_id
            _ = self.clip_store.add_vector(
                StoreItem(
                    id=entity_id,
                    embedding=embedding,
                    payload={"entity_id": entity_id},
                )
            )

            logger.info(f"Successfully stored CLIP embedding for image {entity_id} in Qdrant")

            # Update job status in store database
            if self.job_submission_service:
                self.job_submission_service.update_job_status(
                    job.job_id, job.status, job.error_message
                )

        except Exception as e:
            logger.error(f"Failed to handle CLIP embedding completion for image {entity_id}: {e}")

    @timed
    async def handle_dino_embedding_complete(self, entity_id: int, job: JobResponse) -> None:
        """Handle DINOv2 embedding job completion.

        Extracts embedding and stores in Qdrant (DINO collection) with entity_id as point_id.

        Args:
            entity_id: Image (Entity) ID (used as Qdrant point_id)
            job: Job response from MQTT callback (minimal data, needs full fetch)
        """
        try:
            # Check if job failed
            if job.status == "failed":
                logger.error(
                    f"DINO embedding job {job.job_id} failed for image {entity_id}: "
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

            with tempfile.NamedTemporaryFile(suffix=".npy", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            try:
                await self.compute_client.download_job_file(
                    job_id=job.job_id,
                    file_path=output_path,
                    dest=tmp_path,
                )

                # Load .npy file

                embedding: NDArray[np.float32] = cast(NDArray[np.float32], np.load(tmp_path))

                # Validate embedding dimension (DINOv2-S is 384)
                if embedding.shape[0] != 384:
                    logger.error(
                        f"Invalid embedding dimension for image {entity_id}: expected 384, got {embedding.shape[0]}"
                    )
                    return

            finally:
                # Cleanup temporary file
                if tmp_path.exists():
                    tmp_path.unlink()

            # Store in Qdrant (DINO collection) with entity_id as point_id
            _ = self.dino_store.add_vector(
                StoreItem(
                    id=entity_id,
                    embedding=embedding,
                    payload={"entity_id": entity_id},
                )
            )

            logger.info(f"Successfully stored DINO embedding for image {entity_id} in Qdrant")

            # Update job status in store database
            if self.job_submission_service:
                self.job_submission_service.update_job_status(
                    job.job_id, job.status, job.error_message
                )

        except Exception as e:
            logger.error(f"Failed to handle DINO embedding completion for image {entity_id}: {e}")

    @timed
    async def handle_face_embedding_complete(
        self, face_id: int, entity_id: int, job: JobResponse
    ) -> None:
        """Handle face embedding job completion.

        1. Extract embedding from job output
        2. Search face store for similar faces
        3. If match found: Link face to existing KnownPerson and record all matches
        4. If no match: Create new KnownPerson and add face to store

        Args:
            face_id: Face record ID
            entity_id: Original image Entity ID (for reference/logging)
            job: Job response from MQTT callback (minimal data, needs full fetch)
        """

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
            if not full_job.params or "output_path" not in full_job.params:
                logger.error(f"No output_path found in job {job.job_id} params")
                return

            output_path = cast(str, full_job.params["output_path"])
            with tempfile.NamedTemporaryFile(suffix=".npy", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            try:
                await self.compute_client.download_job_file(
                    job_id=job.job_id,
                    file_path=output_path,
                    dest=tmp_path,
                )
                embedding: NDArray[np.float32] = cast(NDArray[np.float32], np.load(tmp_path))
                if embedding.shape[0] != self.config.face_vector_size:
                    logger.error(
                        f"Invalid embedding dimension for face {face_id}: expected {self.config.face_vector_size}, got {embedding.shape[0]}"
                    )
                    return
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()

            # Search face store for similar faces
            similar_faces = self.face_store.search(
                query_vector=embedding,
                limit=10,
                search_options=SearchPreferences(
                    score_threshold=self.config.face_embedding_threshold
                ),
            )

            # DB Operations (The part that needs retry)
            @with_retry(max_retries=10)
            def process_face_matches_and_linkage():
                db = database.SessionLocal()
                try:
                    # 1. Get Face record
                    face = db.query(Face).filter(Face.id == face_id).first()
                    if not face:
                        logger.error(f"Face {face_id} not found in database")
                        return

                    # 2. Find the best valid match from similar faces
                    valid_best_face = None
                    if similar_faces:
                        for match in similar_faces:
                            candidate_face = db.query(Face).filter(Face.id == match.id).first()
                            if candidate_face:
                                valid_best_face = candidate_face
                                if valid_best_face.known_person_id:
                                    face.known_person_id = valid_best_face.known_person_id
                                    logger.info(
                                        f"Linked face {face_id} to known person {valid_best_face.known_person_id} "
                                        + f"(match: {match.id}, score: {match.score:.3f})"
                                    )
                                    break

                    # 3. Record ALL matches in FaceMatch table
                    if similar_faces:
                        for match in similar_faces:
                            matched_face_in_db = db.query(Face).filter(Face.id == match.id).first()
                            if not matched_face_in_db:
                                continue

                            face_match = FaceMatch(
                                face_id=face_id,
                                matched_face_id=match.id,
                                similarity_score=match.score,
                                created_at=self._now_timestamp(),
                            )
                            db.add(face_match)

                    # 4. If no valid similar face found, create new KnownPerson
                    if not face.known_person_id:
                        known_person = KnownPerson(
                            created_at=self._now_timestamp(),
                            updated_at=self._now_timestamp(),
                        )
                        db.add(known_person)
                        db.flush()
                        face.known_person_id = known_person.id
                        logger.info(
                            f"Created new known person {known_person.id} for face {face_id}"
                        )

                    db.commit()
                except Exception:
                    db.rollback()
                    raise
                finally:
                    db.close()

            process_face_matches_and_linkage()

            # 5. Add face embedding to face store
            p_id = 0
            db_fetch = database.SessionLocal()
            try:
                face_fetch = db_fetch.query(Face).filter(Face.id == face_id).first()
                if face_fetch:
                    p_id = face_fetch.known_person_id or 0
            finally:
                db_fetch.close()

            _ = self.face_store.add_vector(
                StoreItem(
                    id=face_id,
                    embedding=np.array(embedding, dtype=np.float32),
                    payload={
                        "face_id": face_id,
                        "entity_id": entity_id,
                        "known_person_id": p_id,
                    },
                )
            )

            logger.info(f"Successfully processed face embedding for face {face_id}")
