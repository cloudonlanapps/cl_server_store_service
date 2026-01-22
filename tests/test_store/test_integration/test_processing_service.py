import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from store.common import versioning # Must be first
from store.m_insight.intelligence.service import IntelligenceProcessingService
from store.m_insight.models import EntityVersionData
from store.store.config import StoreConfig
from store.m_insight.intelligence.logic.pysdk_config import PySDKRuntimeConfig
from pathlib import Path
from cl_client.models import JobResponse

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def mock_store_config(integration_config):
    return StoreConfig(
        cl_server_dir=Path("/tmp/fake"),
        media_storage_dir=Path("/tmp/fake/media"),
        public_key_path=Path("/tmp/fake/keys/public_key.pem"),
        auth_disabled=True,
        server_port=integration_config.store_port
    )

@pytest.fixture
def mock_pysdk_config():
    return PySDKRuntimeConfig(
        auth_service_url="http://auth",
        compute_service_url="http://compute",
        compute_username="admin",
        compute_password="password",
        qdrant_url="http://qdrant",
        mqtt_broker="localhost",
        mqtt_port=1883
    )

@pytest.fixture
def processing_service(mock_db, mock_store_config, mock_pysdk_config):
    with patch("store.m_insight.intelligence.service.get_qdrant_store"), \
         patch("store.m_insight.intelligence.service.get_dino_store"), \
         patch("store.store.entity_storage.EntityStorageService"):
        return IntelligenceProcessingService(mock_db, mock_store_config, mock_pysdk_config)

@pytest.mark.asyncio
async def test_trigger_async_jobs_missing_file_path(processing_service):
    """Test job triggering when file_path is missing."""
    entity = EntityVersionData(
        id=1,
        transaction_id=1,
        file_path=None
    )
    result = await processing_service.trigger_async_jobs(entity)
    assert result["face_detection_job"] is None

@pytest.mark.asyncio
async def test_trigger_async_jobs_file_not_found(processing_service):
    """Test job triggering when file does not exist."""
    entity = EntityVersionData(
        id=2,
        transaction_id=1,
        file_path="nonexistent.jpg"
    )
    processing_service.file_storage.get_absolute_path.return_value = Path("/nonexistent.jpg")
    # Path("/nonexistent.jpg").exists() will be false
    
    result = await processing_service.trigger_async_jobs(entity)
    assert result["face_detection_job"] is None

@pytest.mark.asyncio
async def test_trigger_async_jobs_success(processing_service):
    """Test successful job triggering."""
    entity = EntityVersionData(
        id=3,
        transaction_id=1,
        file_path="test.jpg"
    )
    
    mock_path = MagicMock(spec=Path)
    mock_path.exists.return_value = True
    mock_path.__str__.return_value = "/tmp/fake/media/test.jpg"
    processing_service.file_storage.get_absolute_path.return_value = mock_path
    
    with patch("store.m_insight.intelligence.service.get_compute_client") as mock_get_compute, \
         patch("store.m_insight.intelligence.service.JobSubmissionService") as mock_job_service_class, \
         patch("store.m_insight.intelligence.service.JobCallbackHandler"):
        
        mock_job_service = mock_job_service_class.return_value
        mock_job_service.submit_face_detection = AsyncMock(return_value="face-1")
        mock_job_service.submit_clip_embedding = AsyncMock(return_value="clip-1")
        mock_job_service.submit_dino_embedding = AsyncMock(return_value="dino-1")
        
        result = await processing_service.trigger_async_jobs(entity)
        
        assert result["face_detection_job"] == "face-1"
        assert result["clip_embedding_job"] == "clip-1"
        assert result["dino_embedding_job"] == "dino-1"
        
        mock_job_service.submit_face_detection.assert_called_once()
        mock_job_service.submit_clip_embedding.assert_called_once()
        mock_job_service.submit_dino_embedding.assert_called_once()

@pytest.mark.asyncio
async def test_processing_callbacks(processing_service):
    """Test internal callbacks of trigger_async_jobs."""
    entity = EntityVersionData(
        id=4,
        transaction_id=1,
        file_path="callback.jpg"
    )
    
    mock_path = MagicMock(spec=Path)
    mock_path.exists.return_value = True
    processing_service.file_storage.get_absolute_path.return_value = mock_path
    
    with patch("store.m_insight.intelligence.service.get_compute_client"), \
         patch("store.m_insight.intelligence.service.JobSubmissionService") as mock_job_service_class, \
         patch("store.m_insight.intelligence.service.JobCallbackHandler") as mock_callback_handler_class:
        
        mock_job_service = mock_job_service_class.return_value
        mock_job_service.submit_face_detection = AsyncMock(return_value="face-1")
        mock_job_service.submit_clip_embedding = AsyncMock(return_value="clip-1")
        mock_job_service.submit_dino_embedding = AsyncMock(return_value="dino-1")
        mock_callback_handler = mock_callback_handler_class.return_value
        mock_callback_handler.handle_face_detection_complete = AsyncMock()
        mock_callback_handler.handle_clip_embedding_complete = AsyncMock()
        mock_callback_handler.handle_dino_embedding_complete = AsyncMock()
        
        await processing_service.trigger_async_jobs(entity)
        
        # Capture the callbacks passed to submit_...
        face_cb = mock_job_service.submit_face_detection.call_args[1]["on_complete_callback"]
        clip_cb = mock_job_service.submit_clip_embedding.call_args[1]["on_complete_callback"]
        dino_cb = mock_job_service.submit_dino_embedding.call_args[1]["on_complete_callback"]
        
        # Mock jobs
        job_face = JobResponse(job_id="f1", status="completed", task_type="face_detection", created_at=0)
        job_clip = JobResponse(job_id="c1", status="completed", task_type="clip_embedding", created_at=0)
        job_dino = JobResponse(job_id="d1", status="completed", task_type="dino_embedding", created_at=0)
        
        # Invoke callbacks
        await face_cb(job_face)
        await clip_cb(job_clip)
        await dino_cb(job_dino)
        
        # Verify status updates and handler calls
        assert mock_job_service.update_job_status.call_count == 3
        mock_callback_handler.handle_face_detection_complete.assert_called_once_with(4, job_face)
        mock_callback_handler.handle_clip_embedding_complete.assert_called_once_with(4, job_clip)
        mock_callback_handler.handle_dino_embedding_complete.assert_called_once_with(4, job_dino)
