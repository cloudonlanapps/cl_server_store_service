import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from store.common import versioning # Must be first
from store.m_insight.intelligence.logic.job_service import JobSubmissionService
from store.m_insight.intelligence.models import EntityJob
from store.common.models import Entity

@pytest.fixture
def mock_compute():
    client = MagicMock()
    return client

@pytest.fixture
def job_service(mock_compute):
    return JobSubmissionService(mock_compute)

@pytest.mark.asyncio
@patch("store.m_insight.intelligence.logic.job_service.EntityJob")
async def test_submit_face_detection(mock_entity_job_class, job_service, mock_compute):
    """Test face detection job submission."""
    mock_response = MagicMock(job_id="job-123")
    mock_compute.face_detection.detect = AsyncMock(return_value=mock_response)
    
    with patch("store.common.database.SessionLocal") as mock_session:
        db = mock_session.return_value
        
        job_id = await job_service.submit_face_detection(
            entity_id=1,
            file_path="/path/to/img.jpg",
            on_complete_callback=lambda x: None
        )
        
        assert job_id == "job-123"
        mock_compute.face_detection.detect.assert_called_once()
        db.add.assert_called_once()
        db.commit.assert_called_once()

@pytest.mark.asyncio
@patch("store.m_insight.intelligence.logic.job_service.EntityJob")
async def test_submit_clip_embedding(mock_entity_job_class, job_service, mock_compute):
    """Test CLIP embedding job submission."""
    mock_response = MagicMock(job_id="clip-123")
    mock_compute.clip_embedding.embed_image = AsyncMock(return_value=mock_response)
    
    with patch("store.common.database.SessionLocal") as mock_session:
        db = mock_session.return_value
        
        job_id = await job_service.submit_clip_embedding(
            entity_id=1,
            file_path="/path/to/img.jpg",
            on_complete_callback=lambda x: None
        )
        
        assert job_id == "clip-123"
        mock_compute.clip_embedding.embed_image.assert_called_once()
        db.add.assert_called_once()

@pytest.mark.asyncio
@patch("store.m_insight.intelligence.logic.job_service.EntityJob")
async def test_submit_dino_embedding(mock_entity_job_class, job_service, mock_compute):
    """Test DINO embedding job submission."""
    mock_response = MagicMock(job_id="dino-123")
    mock_compute.dino_embedding.embed_image = AsyncMock(return_value=mock_response)
    
    with patch("store.common.database.SessionLocal") as mock_session:
        db = mock_session.return_value
        
        job_id = await job_service.submit_dino_embedding(
            entity_id=1,
            file_path="/path/to/img.jpg",
            on_complete_callback=lambda x: None
        )
        
        assert job_id == "dino-123"
        mock_compute.dino_embedding.embed_image.assert_called_once()

def test_delete_job_record(job_service):
    """Test job record deletion."""
    with patch("store.common.database.SessionLocal") as mock_session:
        db = mock_session.return_value
        mock_job = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_job
        
        job_service.delete_job_record("job-123")
        db.delete.assert_called_with(mock_job)
        db.commit.assert_called_once()

def test_update_job_status(job_service):
    """Test job status update."""
    with patch("store.common.database.SessionLocal") as mock_session:
        db = mock_session.return_value
        mock_job = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_job
        
        job_service.update_job_status("job-123", "completed")
        assert mock_job.status == "completed"
        db.commit.assert_called_once()
