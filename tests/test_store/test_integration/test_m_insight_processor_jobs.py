from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from cl_client.models import JobResponse

from store.common import StorageService
from store.m_insight import MediaInsight, MInsightConfig
from store.m_insight.schemas import EntityVersionSchema


@pytest.fixture
def mock_db_session():
    mock = MagicMock()
    # Mock query/filter/first chain
    mock.query.return_value.filter.return_value.first.return_value = MagicMock()
    return mock


@pytest.fixture
def mock_config():
    return MInsightConfig(
        id="test-worker",
        cl_server_dir=Path("/tmp/fake"),
        media_storage_dir=Path("/tmp/fake/media"),
        public_key_path=Path("/tmp/fake/keys/public_key.pem"),
        no_auth=True,
        auth_url="http://auth",
        compute_url="http://compute",
        compute_username="admin",
        compute_password="password",
        qdrant_url="http://qdrant",
        qdrant_collection="clip_embeddings",
        dino_collection="dino_embeddings",
        face_collection="face_embeddings",
        mqtt_url="mqtt://localhost:1883",
        mqtt_topic="test/processor_jobs",
        log_level="INFO",
        store_port=8001,
    )


@pytest_asyncio.fixture
async def processor(mock_config):
    with (
        patch("store.m_insight.media_insight.version_class"),
        patch("store.m_insight.media_insight.database.SessionLocal"),
        patch("store.m_insight.media_insight.configure_mappers"),
    ):
        mock_broadcaster = MagicMock()
        p = MediaInsight(mock_config, broadcaster=mock_broadcaster)

        # Manually initialize services mocks to bypass external calls
        p.storage_service = MagicMock(spec=StorageService)
        p.storage_service.get_absolute_path.side_effect = lambda p: Path(f"/tmp/fake/media/{p}")

        p.job_service = MagicMock()
        p.job_service.submit_face_detection = AsyncMock(return_value="face-1")
        p.job_service.submit_clip_embedding = AsyncMock(return_value="clip-1")
        p.job_service.submit_dino_embedding = AsyncMock(return_value="dino-1")
        p.job_service.broadcast_entity_status = MagicMock()

        p.callback_handler = MagicMock()
        p.callback_handler.handle_face_detection_complete = AsyncMock()
        p.callback_handler.handle_clip_embedding_complete = AsyncMock()
        p.callback_handler.handle_dino_embedding_complete = AsyncMock()

        # Mock db.entity.get to return a valid schema object (or object that can be converted)
        # We need this because JobSubmissionService converts the result to EntitySchema/EntityVersionSchema
        from store.db_service import EntitySchema

        def get_entity_side_effect(id):
            e = MagicMock()
            e.id = id
            e.intelligence_data = None
            e.md5 = "abc"

            # Match behavior to test cases based on ID
            if id == 1:
                e.file_path = None  # Missing file path
            else:
                e.file_path = "test.jpg"  # Valid path for others

            return e

        p.db = MagicMock()
        p.db.entity.get.side_effect = get_entity_side_effect

        # Also need to make sure p.job_service.db is the same mock if it uses it
        p.job_service.db = p.db

        p._initialized = True  # Skip real init

        yield p


@pytest.mark.asyncio
async def test_trigger_async_jobs_missing_file_path(processor):
    """Test job triggering when file_path is missing."""
    entity = EntityVersionSchema(
        id=1, transaction_id=1, file_path=None, type="image", md5="abc", is_deleted=False
    )

    # We are testing private method _trigger_async_jobs directly for unit testing
    await processor._trigger_async_jobs(entity)

    # JobService handles validation, so it SHOULD be called
    processor.job_service.submit_face_detection.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_async_jobs_file_not_found(processor):
    """Test job triggering when file does not exist."""
    entity = EntityVersionSchema(
        id=2,
        transaction_id=1,
        file_path="nonexistent.jpg",
        type="image",
        md5="abc",
        is_deleted=False,
    )

    # Mock path existence failure
    with patch("pathlib.Path.exists", return_value=False):
        await processor._trigger_async_jobs(entity)

    # JobService handles validation, so it SHOULD be called
    processor.job_service.submit_face_detection.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_async_jobs_success(processor):
    """Test successful job triggering."""
    entity = EntityVersionSchema(
        id=3, transaction_id=1, file_path="test.jpg", type="image", md5="abc", is_deleted=False
    )

    # Mock path existence success
    with patch("pathlib.Path.exists", return_value=True):
        await processor._trigger_async_jobs(entity)

    # Verify jobs submitted
    processor.job_service.submit_face_detection.assert_called_once()
    processor.job_service.submit_clip_embedding.assert_called_once()
    processor.job_service.submit_dino_embedding.assert_called_once()


@pytest.mark.asyncio
async def test_processing_callbacks(processor):
    """Test internal callbacks of trigger_async_jobs."""
    entity = EntityVersionSchema(
        id=4, transaction_id=1, file_path="callback.jpg", type="image", md5="abc", is_deleted=False
    )

    with patch("pathlib.Path.exists", return_value=True):
        await processor._trigger_async_jobs(entity)

    # Capture the callbacks passed to submit_...
    face_cb = processor.job_service.submit_face_detection.call_args[1]["on_complete_callback"]
    clip_cb = processor.job_service.submit_clip_embedding.call_args[1]["on_complete_callback"]
    dino_cb = processor.job_service.submit_dino_embedding.call_args[1]["on_complete_callback"]

    # Mock jobs
    job_face = JobResponse(
        job_id="f1", status="completed", task_type="face_detection", created_at=0
    )
    job_clip = JobResponse(
        job_id="c1", status="completed", task_type="clip_embedding", created_at=0
    )
    job_dino = JobResponse(
        job_id="d1", status="completed", task_type="dino_embedding", created_at=0
    )

    # Invoke callbacks
    await face_cb(job_face)
    await clip_cb(job_clip)
    await dino_cb(job_dino)

    # Verify handler calls
    processor.callback_handler.handle_face_detection_complete.assert_called_once_with(4, job_face)
    processor.callback_handler.handle_clip_embedding_complete.assert_called_once_with(4, job_clip)
    processor.callback_handler.handle_dino_embedding_complete.assert_called_once_with(4, job_dino)

    # Verify status updates on job service
    assert processor.job_service.update_job_status.call_count == 3
