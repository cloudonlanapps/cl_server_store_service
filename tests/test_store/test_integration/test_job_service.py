from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from store.m_insight import JobSubmissionService
from store.db_service import EntityIntelligenceData, JobInfo, InferenceStatus




pytestmark = pytest.mark.integration
@pytest.fixture
def mock_compute():
    client = MagicMock()
    return client

@pytest.fixture
def mock_storage():
    return MagicMock()

@pytest.fixture
def job_service(mock_compute, mock_storage):
    js = JobSubmissionService(mock_compute, mock_storage)
    # Mock internal DB service
    js.db = MagicMock()
    return js


@pytest.mark.asyncio
async def test_submit_face_detection(job_service, mock_compute):
    """Test face detection job submission."""
    mock_response = MagicMock(job_id="job-123")
    mock_compute.face_detection.detect = AsyncMock(return_value=mock_response)

    mock_entity = MagicMock()
    mock_entity.id = 1
    mock_entity.file_path = "img.jpg"
    mock_entity.md5 = "abc"
    # Mock existing intelligence_data check
    job_service.db.entity.get.return_value = mock_entity
    job_service.db.intelligence.get_intelligence_data.return_value = None

    # Mock storage resolution
    job_service.storage_service.get_absolute_path.return_value = Path("/path/to/img.jpg")
    
    with patch("pathlib.Path.exists", return_value=True):
        job_id = await job_service.submit_face_detection(
            entity=mock_entity,
            on_complete_callback=lambda x: None
        )

    assert job_id == "job-123"
    mock_compute.face_detection.detect.assert_called_once()
    
    # Verify entity update was called with active job
    job_service.db.intelligence.atomic_update_intelligence_data.assert_called_once()
    args = job_service.db.intelligence.atomic_update_intelligence_data.call_args
    assert args[0][0] == 1 # entity_id
    update_fn = args[0][1]
    
    # Create dummy data and run update_fn to verify its logic
    data = EntityIntelligenceData(last_updated=0)
    update_fn(data)
    assert len(data.active_jobs) == 1
    assert data.active_jobs[0].job_id == "job-123"
    assert data.active_jobs[0].task_type == "face_detection"


@pytest.mark.asyncio
async def test_submit_clip_embedding(job_service, mock_compute):
    """Test CLIP embedding job submission."""
    mock_response = MagicMock(job_id="clip-123")
    mock_compute.clip_embedding.embed_image = AsyncMock(return_value=mock_response)

    mock_entity = MagicMock()
    mock_entity.id = 1
    mock_entity.file_path = "img.jpg"
    mock_entity.md5 = "abc"
    job_service.db.entity.get.return_value = mock_entity
    job_service.db.intelligence.get_intelligence_data.return_value = None

    job_service.storage_service.get_absolute_path.return_value = Path("/path/to/img.jpg")

    job_id = await job_service.submit_clip_embedding(
        entity=mock_entity,
        on_complete_callback=lambda x: None
    )

    assert job_id == "clip-123"
    mock_compute.clip_embedding.embed_image.assert_called_once()
    
    job_service.db.intelligence.atomic_update_intelligence_data.assert_called_once()
    update_fn = job_service.db.intelligence.atomic_update_intelligence_data.call_args[0][1]
    data = EntityIntelligenceData(last_updated=0)
    update_fn(data)
    assert data.active_jobs[0].job_id == "clip-123"


@pytest.mark.asyncio
async def test_submit_dino_embedding(job_service, mock_compute):
    """Test DINO embedding job submission."""
    mock_response = MagicMock(job_id="dino-123")
    mock_compute.dino_embedding.embed_image = AsyncMock(return_value=mock_response)

    mock_entity = MagicMock()
    mock_entity.id = 1
    mock_entity.file_path = "img.jpg"
    mock_entity.md5 = "abc"
    job_service.db.entity.get.return_value = mock_entity
    job_service.db.intelligence.get_intelligence_data.return_value = None

    job_service.storage_service.get_absolute_path.return_value = Path("/path/to/img.jpg")

    job_id = await job_service.submit_dino_embedding(
        entity=mock_entity,
        on_complete_callback=lambda x: None
    )

    assert job_id == "dino-123"
    mock_compute.dino_embedding.embed_image.assert_called_once()
    
    job_service.db.intelligence.atomic_update_intelligence_data.assert_called_once()
    update_fn = job_service.db.intelligence.atomic_update_intelligence_data.call_args[0][1]
    data = EntityIntelligenceData(last_updated=0)
    update_fn(data)
    assert data.active_jobs[0].job_id == "dino-123"

def test_delete_job_record(job_service):
    """Test job record deletion."""
    mock_entity = MagicMock()
    mock_entity.id = 1
    
    # Setup initial intelligence data with a job
    data = EntityIntelligenceData(
        last_updated=0, 
        active_jobs=[JobInfo(job_id="job-123", task_type="test", started_at=0)]
    )
    job_service.db.entity.get.return_value = mock_entity
    # delete_job_record only needs atomic_update, doesn't check get_intelligence_data first explicitly?
    # Actually delete_job_record implementation just calls atomic_update.


    job_service.delete_job_record(1, "job-123")
    
    job_service.db.intelligence.atomic_update_intelligence_data.assert_called_once()
    update_fn = job_service.db.intelligence.atomic_update_intelligence_data.call_args[0][1]
    update_fn(data)
    assert len(data.active_jobs) == 0

def test_update_job_status(job_service):
    """Test job status update."""
    mock_entity = MagicMock()
    mock_entity.id = 1
    
    data = EntityIntelligenceData(
        last_updated=0, 
        active_jobs=[JobInfo(job_id="job-123", task_type="face_detection", started_at=0)],
        inference_status=InferenceStatus(face_detection="processing")
    )
    job_service.db.entity.get.return_value = mock_entity


    job_service.update_job_status(1, "job-123", "completed")
    
    job_service.db.intelligence.atomic_update_intelligence_data.assert_called_once()
    update_fn = job_service.db.intelligence.atomic_update_intelligence_data.call_args[0][1]
    update_fn(data)
    
    # Should update inference status
    assert data.inference_status.face_detection == "completed"
    # Should remove from active jobs (completed)
    assert len(data.active_jobs) == 0
