import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from store.common import Entity, EntityJob, Face, ImageIntelligence, versioning
from store.m_insight import JobCallbackHandler, MInsightConfig
from cl_client.models import JobResponse


@pytest.fixture
def mock_m_insight_config(mock_store_config):
    return MInsightConfig(
        id="test-worker",
        # BaseConfig fields
        cl_server_dir=mock_store_config.cl_server_dir,
        media_storage_dir=mock_store_config.media_storage_dir,
        public_key_path=mock_store_config.public_key_path,
        no_auth=mock_store_config.no_auth,
        
        # MInsightConfig fields
        auth_service_url="http://auth",
        compute_service_url="http://compute",
        compute_username="admin",
        compute_password="password",
        qdrant_url="http://qdrant",
        mqtt_server="localhost",
        mqtt_port=1883
    )

@pytest.fixture
def mock_store_config(integration_config):
    from store.store.config import StoreConfig
    return StoreConfig(
        cl_server_dir=Path("/tmp/fake"),
        media_storage_dir=Path("/tmp/fake/media"),
        public_key_path=Path("/tmp/fake/keys/public_key.pem"),
        no_auth=True,
        port=integration_config.store_port
    )

@pytest.fixture
def callback_handler(mock_m_insight_config):
    mock_compute = MagicMock()
    mock_compute.get_job = AsyncMock()
    mock_qdrant = MagicMock()
    mock_dino = MagicMock()
    return JobCallbackHandler(
        compute_client=mock_compute,
        clip_store=MagicMock(),
        dino_store=MagicMock(),
        face_store=MagicMock(),
        config=mock_m_insight_config,
    )

@pytest.mark.asyncio
async def test_callback_failed_job_status(callback_handler):
    """Test callback when job status is failed."""
    job = JobResponse(
        job_id="job1",
        status="failed",
        task_type="face_detection",
        error_message="Some failure",
        params={"entity_id": 1},
        created_at=1000
    )
    
    with patch("store.common.database.SessionLocal") as mock_session_local:
        with patch("store.m_insight.job_callbacks.logger") as mock_logger:
            await callback_handler.handle_face_detection_complete(image_id=1, job=job)
            assert mock_logger.error.called
            assert "failed for image 1" in mock_logger.error.call_args[0][0]

@pytest.mark.asyncio
async def test_callback_missing_detections(callback_handler):
    """Test callback when detections missing in full job output."""
    job = JobResponse(
        job_id="job2",
        status="completed",
        task_type="face_detection",
        created_at=1000
    )
    
    # Mock compute_client.get_job to return a job without faces
    full_job = JobResponse(
        job_id="job2",
        status="completed",
        task_type="face_detection",
        task_output={}, # Missing faces/detections
        created_at=1000
    )
    callback_handler.compute_client.get_job.return_value = full_job
    
    with patch("store.common.database.SessionLocal") as mock_session_local:
        with patch("store.m_insight.job_callbacks.logger") as mock_logger:
            await callback_handler.handle_face_detection_complete(image_id=1, job=job)
            assert mock_logger.warning.called
            assert "No faces found" in mock_logger.warning.call_args[0][0]

@pytest.mark.asyncio
async def test_callback_entity_not_found(callback_handler):
    """Test callback when entity is not found in database."""
    job = JobResponse(
        job_id="job3",
        status="completed",
        task_type="face_detection",
        created_at=1000
    )
    
    # Needs full_job for logic to proceed to entity query
    full_job = JobResponse(
        job_id="job3",
        status="completed",
        task_type="face_detection",
        task_output={"faces": [{"bbox": {"x1":0,"y1":0,"x2":1,"y2":1}, "file_path":"f.png"}]}, # Need some face to trigger query
        created_at=1000
    )
    callback_handler.compute_client.get_job.return_value = full_job
    
    with patch("store.common.database.SessionLocal") as mock_session_local:
        mock_db = mock_session_local.return_value
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with patch("store.m_insight.job_callbacks.logger") as mock_logger:
            await callback_handler.handle_face_detection_complete(image_id=999, job=job)
            assert mock_logger.error.called
            assert "not found" in mock_logger.error.call_args[0][0].lower()

@pytest.mark.asyncio
async def test_callback_database_error(callback_handler):
    """Test callback behavior on database exception."""
    job = JobResponse(
        job_id="job4",
        status="completed",
        task_type="face_detection",
        created_at=1000
    )
    
    with patch("store.common.database.SessionLocal") as mock_session_local:
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        # Trigger exception inside the try block
        callback_handler.compute_client.get_job.side_effect = Exception("Fetch failed")
        
        with patch("store.m_insight.job_callbacks.logger") as mock_logger:
            await callback_handler.handle_face_detection_complete(image_id=1, job=job)
            assert mock_logger.error.called
            # The actual log message depends on the exception message
            assert "Fetch failed" in mock_logger.error.call_args[0][0]

@pytest.mark.asyncio
async def test_callback_clip_malformed_output(callback_handler):
    """Test CLIP callback with invalid output format."""
    job = JobResponse(
        job_id="job5",
        status="completed",
        task_type="clip_embedding",
        created_at=1000
    )
    
    full_job = JobResponse(
        job_id="job5",
        status="completed",
        task_type="clip_embedding",
        task_output={"embedding": "not a list"}, # Malformed
        created_at=1000
    )
    callback_handler.compute_client.get_job.return_value = full_job
    
    with patch("store.common.database.SessionLocal") as mock_session_local:
        with patch("store.m_insight.job_callbacks.logger") as mock_logger:
            await callback_handler.handle_clip_embedding_complete(image_id=1, job=job)
            assert mock_logger.error.called

@pytest.mark.asyncio
async def test_callback_job_not_found(callback_handler):
    """Test callback when full job fetch returns None."""
    job = JobResponse(job_id="job_none", status="completed", task_type="face_detection", created_at=0)
    # Correctly reset and set return_value on the AsyncMock
    callback_handler.compute_client.get_job = AsyncMock(return_value=None)
    
    with patch("store.common.database.SessionLocal"), \
         patch("store.m_insight.job_callbacks.logger") as mock_logger:
        await callback_handler.handle_face_detection_complete(image_id=1, job=job)
        assert mock_logger.warning.called
        assert "not completed when fetching" in mock_logger.warning.call_args[0][0]

@pytest.mark.asyncio
async def test_callback_validation_error(callback_handler):
    """Test callback when task_output fails pydantic validation."""
    job = JobResponse(job_id="job_val", status="completed", task_type="face_detection", created_at=0)
    full_job = JobResponse(
        job_id="job_val", 
        status="completed", 
        task_type="face_detection", 
        task_output={"faces": "invalid_type"}, # Should be list
        created_at=0
    )
    callback_handler.compute_client.get_job = AsyncMock(return_value=full_job)
    
    with patch("store.common.database.SessionLocal") as mock_session_local:
        db = mock_session_local.return_value
        db.query.return_value.filter.return_value.first.return_value = MagicMock(id=1, create_date=1000)
        
        with patch("store.m_insight.job_callbacks.logger") as mock_logger:
            await callback_handler.handle_face_detection_complete(image_id=1, job=job)
            assert mock_logger.error.called
            assert "Invalid task_output format" in mock_logger.error.call_args[0][0]

@pytest.mark.asyncio
async def test_callback_entity_date_fallback(callback_handler):
    """Test callback date fallback when entity has no create_date."""
    job = JobResponse(job_id="job_date", status="completed", task_type="face_detection", created_at=0)
    full_job = JobResponse(
        job_id="job_date", 
        status="completed", 
        task_type="face_detection", 
        task_output={
            "faces": [{
                "bbox": {"x1":0, "y1":0, "x2":1, "y2":1},
                "file_path": "f.png",
                "landmarks": {
                    "right_eye": [0,0], "left_eye": [0,0], "nose_tip": [0,0], "mouth_right": [0,0], "mouth_left": [0,0]
                },
                "confidence": 0.99
            }],
            "num_faces": 1,
            "image_width": 100,
            "image_height": 100
        },
        created_at=0
    )
    callback_handler.compute_client.get_job = AsyncMock(return_value=full_job)
    
    with patch("store.common.database.SessionLocal") as mock_session_local:
        db = mock_session_local.return_value
        mock_entity = MagicMock()
        mock_entity.id = 1
        mock_entity.create_date = None
        mock_entity.updated_date = 2000000000
        db.query.return_value.filter.return_value.first.return_value = mock_entity
        
        # Patch the method using the actual handler instance to ensure it's captured
        with patch.object(callback_handler, "_get_face_storage_path", return_value=Path("/tmp/face.png")) as mock_get_path:
            await callback_handler.handle_face_detection_complete(image_id=1, job=job)
            assert mock_get_path.called
            # args[2] is entity_create_date
            args, _ = mock_get_path.call_args
            assert args[2] == 2000000000
