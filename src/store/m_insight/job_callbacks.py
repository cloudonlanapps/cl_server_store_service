from __future__ import annotations

import asyncio
import functools
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

from store.db_service import DBService
from store.db_service.schemas import EntityIntelligenceData, FaceSchema, JobInfo
from store.vectorstore_services.schemas import StoreItem
from store.vectorstore_services.vector_stores import QdrantVectorStore

from .config import FACE_VECTOR_SIZE, MInsightConfig
from .job_service import JobSubmissionService


def with_entity_lock(func):
    """Decorator to wrap callback with entity-level lock for serialization.

    This ensures only one callback runs at a time for a given entity,
    preventing all race conditions in intelligence_data updates.
    """

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        # Extract entity_id from kwargs or positional args
        # Check both handle_face_embedding_complete(face_id, entity_id, ...)
        # and other callbacks(entity_id, ...)
        if "entity_id" in kwargs:
            entity_id = kwargs["entity_id"]
        elif len(args) >= 2 and func.__name__ == "handle_face_embedding_complete":
            # For handle_face_embedding_complete: (face_id, entity_id, job, face_index)
            entity_id = args[1]
        elif len(args) >= 1:
            # For other callbacks: (entity_id, job)
            entity_id = args[0]
        else:
            raise ValueError(f"Could not extract entity_id from {func.__name__} arguments")

        lock = await self._get_entity_lock(entity_id)
        async with lock:
            logger.debug(f"[{func.__name__}] Acquired lock for entity {entity_id}")
            try:
                result = await func(self, *args, **kwargs)
                return result
            finally:
                logger.debug(f"[{func.__name__}] Released lock for entity {entity_id}")

    return wrapper


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
        db: DBService,
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
        self.db = db
        self.job_submission_service: JobSubmissionService | None = job_submission_service
        # Per-entity locks to serialize callbacks for the same entity
        self._entity_locks: dict[int, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()  # Lock for accessing the locks dict

    async def _get_entity_lock(self, entity_id: int) -> asyncio.Lock:
        """Get or create lock for specific entity.

        Args:
            entity_id: Entity ID

        Returns:
            asyncio.Lock for this entity
        """
        async with self._locks_lock:
            if entity_id not in self._entity_locks:
                self._entity_locks[entity_id] = asyncio.Lock()
            return self._entity_locks[entity_id]

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

    async def _verify_job_safety(self, entity_id: int, job_id: str) -> bool:
        """Verify if job should be processed (safety checks)."""
        logger.debug(f"[_verify_job_safety] Checking entity {entity_id}, job {job_id}")
        entity = self.db.entity.get(entity_id)
        if not entity:
            logger.info(f"Entity {entity_id} no longer exists, skipping callback for job {job_id}")
            return False

        if entity.is_deleted:
            logger.warning(f"Entity {entity_id} is deleted, skipping results for job {job_id}")
            return False

        data = self.db.intelligence.get_intelligence_data(entity_id)
        if not data:
            logger.warning(f"Entity {entity_id} has no intelligence_data, skipping job {job_id}")
            return False

        # Safety Check: Job must be active
        active_job_ids = [j.job_id for j in data.active_jobs]
        logger.debug(f"[_verify_job_safety] Entity {entity_id} active_jobs: {active_job_ids}")
        if not any(j.job_id == job_id for j in data.active_jobs):
            logger.warning(
                f"Job {job_id} is no longer active for entity {entity_id}, discarding stale results. Active jobs: {active_job_ids}"
            )
            return False

        # Safety Check: MD5 must match
        if data.active_processing_md5 != entity.md5:
            logger.warning(
                f"Entity {entity_id} MD5 changed (was {data.active_processing_md5}, now {entity.md5}), discarding stale results"
            )
            # Cleanup job record
            # if self.job_submission_service:
            #    self.job_submission_service.delete_job_record(entity_id, job_id)
            return False

        return True

    def _get_face_storage_path(self, entity_id: int, face_index: int) -> Path:
        """Get storage path for face image using entity ID.

        Args:
            entity_id: Image (Entity) ID
            face_index: Face index (0, 1, 2, ...)

        Returns:
            Path to face image file
        """
        base_dir = self.config.media_storage_dir
        dir_path = base_dir / "faces" / str(entity_id)
        _ = dir_path.mkdir(parents=True, exist_ok=True)

        # Filename: {index}.png
        filename = f"{face_index}.png"

        return dir_path / filename

    @timed
    @with_entity_lock
    async def handle_face_detection_complete(self, entity_id: int, job: JobResponse) -> None:
        """Handle face detection job completion.

        Downloads cropped faces, saves to files, and creates Face records in database.

        Args:
            entity_id: Image (Entity) ID
            job: Job response from MQTT callback (minimal data, needs full fetch)
        """
        logger.info(f"[TRACE] handle_face_detection_complete called: entity_id={entity_id}, job_id={job.job_id}")

        try:
            # Phase 1: Download face images and create/update Face records
            # Check if job failed
            if job.status == "failed":
                logger.error(
                    f"Face detection job {job.job_id} failed for image {entity_id}: "
                    + f"{job.error_message}"
                )
                return

            if not await self._verify_job_safety(entity_id, job.job_id):
                return

            # MQTT callbacks don't include task_output - fetch full job via HTTP
            full_job = await self.compute_client.get_job(job.job_id)
            if not full_job or full_job.status != "completed":
                logger.warning(f"Job {job.job_id} not completed when fetching full details")
                return

            # Extract faces from task_output
            if not full_job.task_output or "faces" not in full_job.task_output:
                logger.warning(f"No faces found in job {job.job_id} output for image {entity_id}")
                return

            try:
                task_output = FaceDetectionOutput.model_validate(full_job.task_output)
                faces_data = task_output.faces
                logger.info(f"[TRACE] Job {job.job_id} has {len(faces_data)} faces, will save to entity_id={entity_id}")
            except ValidationError as e:
                logger.error(f"Invalid task_output format for job {job.job_id}: {e}")
                return

            if not faces_data:
                logger.warning(f"No faces found in job output for image {entity_id}")
                # Update job status as completed (with 0 faces) so the pipeline doesn't stall
                if self.job_submission_service:
                    self.job_submission_service.update_job_status(
                        entity_id, job.job_id, "completed", None, job.completed_at
                    )
                return

            entity = self.db.entity.get(
                entity_id
            )  # Already checked in verify_job_safety but need for schema
            if not entity:
                return

            data = self.db.intelligence.get_intelligence_data(entity_id)
            if not data:
                return

            # 2. Downloads
            face_schemas: list[FaceSchema] = []
            for index, face_data in enumerate(faces_data):
                face_path = self._get_face_storage_path(entity_id, index)
                await self._download_face_image(
                    job_id=job.job_id,
                    file_path=face_data.file_path,
                    dest=face_path,
                )

                face_id = entity_id * 10000 + index
                relative_path = face_path.relative_to(self.config.media_storage_dir)

                face_schemas.append(
                    FaceSchema(
                        id=face_id,
                        entity_id=entity_id,
                        bbox=face_data.bbox,
                        confidence=face_data.confidence,
                        landmarks=face_data.landmarks,
                        file_path=str(relative_path),
                        created_at=self._now_timestamp(),
                    )
                )

            # 3. Batch DB Transaction
            logger.info(f"[TRACE] Saving {len(face_schemas)} faces to DB for entity_id={entity_id}, face_ids={[f.id for f in face_schemas]}")
            self.db.face.create_many(face_schemas, ignore_exception=True)
            logger.info(f"[TRACE] Successfully saved {len(face_schemas)} faces for entity_id={entity_id}")

            # Update intelligence_data before submitting next jobs (atomically)
            face_count = len(face_schemas)

            def update_face_data(data):
                """Update function for atomic update."""
                data.face_count = face_count
                data.inference_status.face_embeddings = ["pending"] * face_count

            self.db.intelligence.atomic_update_intelligence_data(entity_id, update_face_data)

            # Phase 2: Submit face_embedding jobs
            if self.job_submission_service:
                for index, f_schema in enumerate(face_schemas):
                    try:

                        async def face_embedding_callback(
                            job_resp: JobResponse, fid: int = f_schema.id, idx: int = index
                        ) -> None:
                            await self.handle_face_embedding_complete(
                                face_id=fid, entity_id=entity_id, job=job_resp, face_index=idx
                            )
                            if self.job_submission_service:
                                self.job_submission_service.update_job_status(
                                    entity_id,
                                    job_resp.job_id,
                                    job_resp.status,
                                    job_resp.error_message,
                                    job_resp.completed_at,
                                )

                        await self.job_submission_service.submit_face_embedding(
                            face=f_schema,
                            entity=entity,
                            on_complete_callback=face_embedding_callback,
                        )

                    except Exception as e:
                        logger.error(
                            f"Failed to submit face_embedding job for face {f_schema.id}: {e}"
                        )

            # Update job status in store database
            if self.job_submission_service:
                self.job_submission_service.update_job_status(
                    entity_id, job.job_id, job.status, job.error_message, job.completed_at
                )

        except Exception as e:
            logger.error(
                f"Unexpected error in handle_face_detection_complete for image {entity_id}: {e}"
            )

    @timed
    @with_entity_lock
    async def handle_clip_embedding_complete(self, entity_id: int, job: JobResponse) -> None:
        """Handle CLIP embedding job completion.

        Extracts embedding and stores in Qdrant with entity_id as point_id.

        Args:
            entity_id: Image (Entity) ID (used as Qdrant point_id)
            job: Job response from MQTT callback (minimal data, needs full fetch)
        """
        try:
            if not await self._verify_job_safety(entity_id, job.job_id):
                return

            # MQTT callbacks don't include task_output - fetch full job via HTTP
            full_job = await self.compute_client.get_job(job.job_id)
            if not full_job or full_job.status != "completed":
                logger.warning(f"Job {job.job_id} not completed when fetching full details")
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

                embedding = cast(NDArray[np.float32], np.load(tmp_path))

                # Validate embedding dimension
                if embedding.shape[0] != 512:
                    logger.error(
                        f"Invalid dimension for image {entity_id}: expected 512, got {embedding.shape[0]}"
                    )
                    return

            finally:
                if tmp_path.exists():
                    tmp_path.unlink()

            # Store in Qdrant
            _ = self.clip_store.add_vector(
                StoreItem(id=entity_id, embedding=embedding, payload={"entity_id": entity_id})
            )
            logger.info(f"Successfully stored CLIP embedding for image {entity_id}")

            # Update job status in store database
            if self.job_submission_service:
                self.job_submission_service.update_job_status(
                    entity_id, job.job_id, job.status, job.error_message, job.completed_at
                )

        except Exception as e:
            logger.error(f"Failed to handle CLIP embedding completion for image {entity_id}: {e}")

    @timed
    @with_entity_lock
    async def handle_dino_embedding_complete(self, entity_id: int, job: JobResponse) -> None:
        """Handle DINOv2 embedding job completion.

        Extracts embedding and stores in Qdrant (DINO collection) with entity_id as point_id.

        Args:
            entity_id: Image (Entity) ID (used as Qdrant point_id)
            job: Job response from MQTT callback (minimal data, needs full fetch)
        """
        try:
            if not await self._verify_job_safety(entity_id, job.job_id):
                return

            # MQTT callbacks don't include task_output - fetch full job via HTTP
            full_job = await self.compute_client.get_job(job.job_id)
            if not full_job or full_job.status != "completed":
                logger.warning(f"Job {job.job_id} not completed when fetching full details")
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

                embedding = cast(NDArray[np.float32], np.load(tmp_path))

                # Validate embedding dimension (DINOv2-S is 384)
                if embedding.shape[0] != 384:
                    logger.error(
                        f"Invalid dimension for image {entity_id}: expected 384, got {embedding.shape[0]}"
                    )
                    return

            finally:
                if tmp_path.exists():
                    tmp_path.unlink()

            # Store in Qdrant
            _ = self.dino_store.add_vector(
                StoreItem(id=entity_id, embedding=embedding, payload={"entity_id": entity_id})
            )
            logger.info(f"Successfully stored DINO embedding for image {entity_id}")

            # Update job status in store database
            if self.job_submission_service:
                self.job_submission_service.update_job_status(
                    entity_id, job.job_id, job.status, job.error_message, job.completed_at
                )

        except Exception as e:
            logger.error(f"Failed to handle DINO embedding completion for image {entity_id}: {e}")

    @timed
    @with_entity_lock
    async def handle_face_embedding_complete(
        self, face_id: int, entity_id: int, job: JobResponse, face_index: int
    ) -> None:
        """Handle face embedding job completion."""

        logger.info(
            f"[handle_face_embedding_complete] ENTERED: face_id={face_id}, entity_id={entity_id}, job_id={job.job_id}, face_index={face_index}, status={job.status}"
        )

        try:
            # Check if job failed
            if job.status == "failed":
                logger.error(
                    f"Face embedding job {job.job_id} failed for face {face_id}: {job.error_message}"
                )
                return

            logger.info(
                f"[handle_face_embedding_complete] About to verify job safety for entity {entity_id}, job {job.job_id}"
            )
            if not await self._verify_job_safety(entity_id, job.job_id):
                logger.warning(
                    f"[handle_face_embedding_complete] Job safety check FAILED for entity {entity_id}, job {job.job_id}"
                )
                return
            logger.info(
                f"[handle_face_embedding_complete] Job safety check PASSED for entity {entity_id}, job {job.job_id}"
            )

            # MQTT callbacks don't include task_output - fetch full job via HTTP
            full_job = await self.compute_client.get_job(job.job_id)
            if not full_job or full_job.status != "completed":
                logger.warning(f"Job {job.job_id} not completed when fetching full details")
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
                embedding = cast(NDArray[np.float32], np.load(tmp_path))
                if embedding.shape[0] != FACE_VECTOR_SIZE:
                    logger.error(
                        f"Invalid dimension for face {face_id}: expected {FACE_VECTOR_SIZE}, got {embedding.shape[0]}"
                    )
                    return
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()

            # Store in Qdrant
            _ = self.face_store.add_vector(
                StoreItem(
                    id=face_id,
                    embedding=np.array(embedding, dtype=np.float32),
                    payload={"face_id": face_id, "entity_id": entity_id},
                )
            )

            # Update intelligence_data face status atomically
            def update_face_status(data):
                """Update function for atomic update."""
                if data.inference_status.face_embeddings is not None and face_index < len(
                    data.inference_status.face_embeddings
                ):
                    old_status = data.inference_status.face_embeddings.copy()
                    data.inference_status.face_embeddings[face_index] = "completed"
                    logger.debug(
                        f"[handle_face_embedding_complete] Entity {entity_id}, Face {face_id} (index={face_index}): "
                        f"Updating face_embeddings from {old_status} to {data.inference_status.face_embeddings}"
                    )

            self.db.intelligence.atomic_update_intelligence_data(entity_id, update_face_status)

            logger.info(f"Successfully processed face embedding for face {face_id}")

        except Exception as e:
            logger.error(f"Failed to handle Face embedding completion for face {face_id}: {e}")
