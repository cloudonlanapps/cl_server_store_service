from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from cl_client.models import JobResponse
from sqlalchemy.orm import Session

from store.common import database, models
from store.common import models as intelligence_models
from store.m_insight import JobCallbackHandler, JobSubmissionService, MInsightConfig


@pytest.fixture(autouse=True)
def override_session_local(test_engine):
    """Override database.SessionLocal to use the test engine."""
    from sqlalchemy.orm import sessionmaker
    import store.common.database as db
    original_session_local = getattr(db, "SessionLocal", None)
    db.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    yield
    if original_session_local:
        db.SessionLocal = original_session_local
    else:
        del db.SessionLocal

class TestJobProcessing:
    @pytest.fixture
    def mock_store_config(self, clean_data_dir):
        from store.store.config import StoreConfig
        return StoreConfig(
            cl_server_dir=clean_data_dir,
            media_storage_dir=clean_data_dir / "media",
            public_key_path=clean_data_dir / "keys" / "public_key.pem",
            no_auth=True,
            port=8001
        )

    @pytest.mark.asyncio
    async def test_job_submission_face_detection(self, test_db_session: Session):
        """Test submitting a face detection job creates an EntityJob record."""
        # Create entity
        entity = models.Entity(label="test.jpg", md5="md5_1", is_collection=False, file_path="test.jpg")
        test_db_session.add(entity)
        test_db_session.commit()

        # Mock compute client
        mock_compute = MagicMock()
        mock_compute.face_detection.detect = AsyncMock(return_value=JobResponse(
            job_id="job_123", status="queued", task_type="face_detection", created_at=0
        ))

        mock_storage = MagicMock()
        mock_storage.get_absolute_path.return_value = Path("/path/to/test.jpg")
        service = JobSubmissionService(mock_compute, mock_storage)
        callback = AsyncMock()

        with patch("pathlib.Path.exists", return_value=True):
            job_id = await service.submit_face_detection(entity, callback)

        assert job_id == "job_123"
        # Verify DB record
        job_record = test_db_session.query(intelligence_models.EntityJob).filter_by(job_id="job_123").first()
        assert job_record is not None
        assert job_record.entity_id == entity.id
        assert job_record.task_type == "face_detection"
        assert job_record.status == "queued"

    @pytest.mark.asyncio
    async def test_face_detection_callback_success(
        self, test_db_session: Session, integration_config, clean_data_dir, mock_store_config
    ):
        """Test handling a successful face detection callback."""
        # Setup data
        entity = models.Entity(label="test.jpg", md5="md5_cc", is_collection=False, create_date=1000)
        test_db_session.add(entity)
        test_db_session.commit()

        job_record = intelligence_models.EntityJob(
            entity_id=entity.id,
            job_id="job_det_1",
            task_type="face_detection",
            status="queued",
            created_at=0,
            updated_at=0
        )
        test_db_session.add(job_record)
        test_db_session.commit()

        # Mock ComputeClient
        mock_compute = AsyncMock()

        # Mock task_output
        landmarks = {
            "right_eye": [0.1, 0.1],
            "left_eye": [0.2, 0.1],
            "nose_tip": [0.15, 0.2],
            "mouth_right": [0.1, 0.3],
            "mouth_left": [0.2, 0.3]
        }
        bbox = {"x1": 0.05, "y1": 0.05, "x2": 0.25, "y2": 0.35}

        detected_face = {
            "bbox": bbox,
            "confidence": 0.99,
            "landmarks": landmarks,
            "file_path": "faces/face_0.png"
        }

        task_output = {
            "faces": [detected_face],
            "num_faces": 1,
            "image_width": 1000,
            "image_height": 1000
        }

        mock_compute.get_job.return_value = MagicMock(
            status="completed",
            task_output=task_output
        )
        mock_compute.download_job_file = AsyncMock()

        # Mock stores
        mock_qdrant = MagicMock()
        mock_dino = MagicMock()

        # Mock job submission service for follow-up jobs
        mock_sub_service = MagicMock()
        mock_sub_service.submit_face_embedding = AsyncMock(return_value="job_emb_1")

        # Ensure delete_job_record actually deletes from the test DB
        def mock_delete(job_id):
            test_db_session.query(intelligence_models.EntityJob).filter_by(job_id=job_id).delete()
            test_db_session.commit()
        mock_sub_service.delete_job_record = MagicMock(side_effect=mock_delete)

        mock_config = MInsightConfig(
            id="test",
            cl_server_dir=clean_data_dir,
            media_storage_dir=clean_data_dir / "media",
            public_key_path=clean_data_dir / "keys" / "public_key.pem",
            face_embedding_threshold=0.7,
            mqtt_broker="localhost",
            mqtt_port=1883
        )

        handler = JobCallbackHandler(
            compute_client=mock_compute,
            clip_store=mock_qdrant,
            dino_store=mock_dino,
            config=mock_config,
            # pysdk_config removed
            job_submission_service=mock_sub_service,
            face_store=MagicMock()
        )

        # Trigger callback
        job_resp = JobResponse(job_id="job_det_1", status="completed", task_type="face_detection", created_at=0)
        await handler.handle_face_detection_complete(entity.id, job_resp)

        # Verify Face record created
        face = test_db_session.query(intelligence_models.Face).filter_by(entity_id=entity.id).first()
        assert face is not None
        assert face.confidence == 0.99
        assert "x1" in face.bbox

        # Verify face embedding job was submitted
        mock_sub_service.submit_face_embedding.assert_called_once()

        # Verify job record is present (status remains queued in this test as handler logic doesn't update it)
        job_record = test_db_session.query(intelligence_models.EntityJob).filter_by(job_id="job_det_1").first()
        assert job_record is not None
        # assert job_record.status == "completed" # Handler does not update status, MediaInsight wrapper does

    @pytest.mark.asyncio
    async def test_clip_embedding_callback_success(
        self, test_db_session: Session, clean_data_dir, mock_store_config
    ):
        """Test handling a successful CLIP embedding callback."""
        entity = models.Entity(label="clip.jpg", md5="md5_clip", is_collection=False)
        test_db_session.add(entity)
        test_db_session.commit()

        mock_compute = AsyncMock()
        # Mock .npy file download
        embedding_data = np.random.rand(512).astype(np.float32)

        async def mock_download(job_id, file_path, dest):
            np.save(dest, embedding_data)

        mock_compute.download_job_file = mock_download
        mock_compute.get_job.return_value = MagicMock(
            status="completed",
            params={"output_path": "embedding.npy"}
        )

        mock_qdrant = MagicMock()
        mock_dino = MagicMock()
        mock_config = MInsightConfig(
            id="test", cl_server_dir=Path("."), media_storage_dir=Path("."), public_key_path=Path("."), mqtt_broker="lh", mqtt_port=123
        ) # Minimal mock

        handler = JobCallbackHandler(
             compute_client=mock_compute,
             clip_store=mock_qdrant,
             dino_store=mock_dino,
             face_store=MagicMock(),
             config=mock_config
        )
        # Note: handler expects config 4th arg.
        # previous code: JobCallbackHandler(..., mock_store_config, mock_pysdk)
        # new code: JobCallbackHandler(..., mock_config) (signatures changed? no, just config)
        # Wait, constructor is (self, compute, clip, dino, face, config, job_sub)
        # In test_job_processing.py line 189 it was doing:
        # handler = JobCallbackHandler(mock_compute, mock_qdrant, mock_dino, mock_store_config, mock_pysdk)
        # This means old signature was different.
        # Current signature (from view_file): (compute, clip, dino, face, config, job_sub)
        # The test line 189 passes 5 args + implicit self.
        # It's missing 'face_store'.
        # I need to fix the call site to match new signature.


        job_resp = JobResponse(job_id="job_clip_1", status="completed", task_type="clip_embedding", created_at=0)
        await handler.handle_clip_embedding_complete(entity.id, job_resp)

        # Verify Qdrant storage
        mock_qdrant.add_vector.assert_called_once()
        call_args = mock_qdrant.add_vector.call_args[0][0]
        assert call_args.id == entity.id
        assert np.allclose(call_args.embedding, embedding_data)

    @pytest.mark.asyncio
    async def test_face_embedding_callback_new_person(
        self, test_db_session: Session, clean_data_dir, mock_store_config
    ):
        """Test face embedding callback creating a new KnownPerson."""
        # 1. Setup Entity and Face
        entity = models.Entity(label="img.jpg", md5="m1", is_collection=False)
        test_db_session.add(entity)
        test_db_session.commit()

        face = intelligence_models.Face(
            id=1001,
            entity_id=entity.id,
            bbox='{"x1":0,"y1":0,"x2":1,"y2":1}',
            confidence=1.0,
            landmarks='{"right_eye":[0,0],"left_eye":[0,0],"nose_tip":[0,0],"mouth_right":[0,0],"mouth_left":[0,0]}',
            file_path="f.png",
            created_at=0
        )
        test_db_session.add(face)
        test_db_session.commit()

        # 2. Mock Compute and stores
        mock_compute = AsyncMock()
        embedding_data = np.random.rand(512).astype(np.float32)
        async def mock_download(job_id, file_path, dest):
            np.save(dest, embedding_data)
        mock_compute.download_job_file = mock_download
        mock_compute.get_job.return_value = MagicMock(
            status="completed",
            params={"output_path": "emb.npy"}
        )

        mock_qdrant = MagicMock()
        mock_face_store = MagicMock()
        mock_face_store.search.return_value = [] # No matches

        mock_config = MInsightConfig(
             id="test", cl_server_dir=Path("."), media_storage_dir=Path("."), public_key_path=Path("."), mqtt_broker="lh", mqtt_port=123,
             face_embedding_threshold=0.7
        )

        handler = JobCallbackHandler(
             compute_client=mock_compute,
             clip_store=mock_qdrant,
             dino_store=MagicMock(),
             face_store=mock_face_store,
             config=mock_config
        )

        # with patch("store.m_insight.intelligence.logic.face_store_singleton.get_face_store", return_value=mock_face_store):
        job_resp = JobResponse(job_id="job_fe_1", status="completed", task_type="face_embedding", created_at=0)
        await handler.handle_face_embedding_complete(face.id, entity.id, job_resp)

        # 3. Verify KnownPerson created and linked
        test_db_session.refresh(face)
        assert face.known_person_id is not None

        person = test_db_session.query(intelligence_models.KnownPerson).filter_by(id=face.known_person_id).first()
        assert person is not None

        # 4. Verify vector store update
        mock_face_store.add_vector.assert_called_once()

    @pytest.mark.asyncio
    async def test_dino_embedding_callback_success(
        self, test_db_session: Session, clean_data_dir, mock_store_config
    ):
        """Test handling a successful DINO embedding callback."""
        entity = models.Entity(label="dino.jpg", md5="md5_dino", is_collection=False)
        test_db_session.add(entity)
        test_db_session.commit()

        mock_compute = AsyncMock()
        embedding_data = np.random.rand(384).astype(np.float32) # DINO is 384
        async def mock_download(job_id, file_path, dest):
            np.save(dest, embedding_data)

        mock_compute.download_job_file = mock_download
        mock_compute.get_job.return_value = MagicMock(
            status="completed",
            params={"output_path": "dino.npy"}
        )

        mock_qdrant = MagicMock()
        mock_dino = MagicMock()
        mock_config = MInsightConfig(
             id="test", cl_server_dir=Path("."), media_storage_dir=Path("."), public_key_path=Path("."), mqtt_broker="lh", mqtt_port=123
        )

        handler = JobCallbackHandler(
             compute_client=mock_compute,
             clip_store=mock_qdrant,
             dino_store=mock_dino,
             face_store=MagicMock(),
             config=mock_config
        )

        job_resp = JobResponse(job_id="job_dino_1", status="completed", task_type="dino_embedding", created_at=0)
        await handler.handle_dino_embedding_complete(entity.id, job_resp)

        # Verify DINO store storage
        mock_dino.add_vector.assert_called_once()

    @pytest.mark.asyncio
    async def test_job_status_updates(self, test_db_session: Session):
        """Test updating job status in DB."""
        # Create entity and job
        entity = models.Entity(label="stat.jpg", md5="m_stat", is_collection=False)
        test_db_session.add(entity)
        test_db_session.commit()

        job = intelligence_models.EntityJob(
            entity_id=entity.id,
            job_id="job_stat_1",
            task_type="face_detection",
            status="queued",
            created_at=0,
            updated_at=0
        )
        test_db_session.add(job)
        test_db_session.commit()

        service = JobSubmissionService(MagicMock(), MagicMock())
        service.update_job_status("job_stat_1", "completed")

        test_db_session.refresh(job)
        assert job.status == "completed"
        assert job.completed_at is not None

        service.update_job_status("job_stat_1", "failed", error_message="Something went wrong")
        test_db_session.refresh(job)
        assert job.status == "failed"
        assert job.error_message == "Something went wrong"
