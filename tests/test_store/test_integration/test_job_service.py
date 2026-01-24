from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from store.m_insight import JobSubmissionService


@pytest.fixture
def mock_compute():
    client = MagicMock()
    return client

@pytest.fixture

def mock_storage():
    return MagicMock()

@pytest.fixture
def job_service(mock_compute, mock_storage):
    return JobSubmissionService(mock_compute, mock_storage)

@pytest.mark.asyncio
@patch("store.m_insight.job_service.EntityJob")
async def test_submit_face_detection(mock_entity_job_class, job_service, mock_compute):
    """Test face detection job submission."""
    mock_response = MagicMock(job_id="job-123")
    mock_compute.face_detection.detect = AsyncMock(return_value=mock_response)

    with patch("store.db_service.database.SessionLocal") as mock_session:
        db = mock_session.return_value

        mock_entity = MagicMock()
        mock_entity.id = 1
        mock_entity.file_path = "img.jpg"

        # Mock storage resolution
        job_service.storage_service.get_absolute_path.return_value = Path("/path/to/img.jpg")
        with patch("pathlib.Path.exists", return_value=True):
            job_id = await job_service.submit_face_detection(
                entity=mock_entity,
                on_complete_callback=lambda x: None
            )

        assert job_id == "job-123"
        mock_compute.face_detection.detect.assert_called_once()
        db.add.assert_called_once()
        db.commit.assert_called_once()

@pytest.mark.asyncio
@patch("store.m_insight.job_service.EntityJob")
async def test_submit_clip_embedding(mock_entity_job_class, job_service, mock_compute):
    """Test CLIP embedding job submission."""
    mock_response = MagicMock(job_id="clip-123")
    mock_compute.clip_embedding.embed_image = AsyncMock(return_value=mock_response)

    with patch("store.db_service.database.SessionLocal") as mock_session:
        db = mock_session.return_value

        mock_entity = MagicMock()
        mock_entity.id = 1
        mock_entity.file_path = "img.jpg"

        job_service.storage_service.get_absolute_path.return_value = Path("/path/to/img.jpg")

        job_id = await job_service.submit_clip_embedding(
            entity=mock_entity,
            on_complete_callback=lambda x: None
        )

        assert job_id == "clip-123"
        mock_compute.clip_embedding.embed_image.assert_called_once()
        db.add.assert_called_once()

@pytest.mark.asyncio
@patch("store.m_insight.job_service.EntityJob")
async def test_submit_dino_embedding(mock_entity_job_class, job_service, mock_compute):
    """Test DINO embedding job submission."""
    mock_response = MagicMock(job_id="dino-123")
    mock_compute.dino_embedding.embed_image = AsyncMock(return_value=mock_response)

    with patch("store.db_service.database.SessionLocal") as mock_session:
        db = mock_session.return_value

        mock_entity = MagicMock()
        mock_entity.id = 1
        mock_entity.file_path = "img.jpg"

        job_service.storage_service.get_absolute_path.return_value = Path("/path/to/img.jpg")

        job_id = await job_service.submit_dino_embedding(
            entity=mock_entity,
            on_complete_callback=lambda x: None
        )

        assert job_id == "dino-123"
        mock_compute.dino_embedding.embed_image.assert_called_once()

def test_delete_job_record(job_service):
    """Test job record deletion."""
    with patch("store.db_service.database.SessionLocal") as mock_session:
        db = mock_session.return_value
        mock_job = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_job

        job_service.delete_job_record("job-123")
        db.delete.assert_called_with(mock_job)
        db.commit.assert_called_once()

def test_update_job_status(job_service):
    """Test job status update."""
    with patch("store.db_service.database.SessionLocal") as mock_session:
        db = mock_session.return_value
        mock_job = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_job

        job_service.update_job_status("job-123", "completed")
        assert mock_job.status == "completed"
        db.commit.assert_called_once()
