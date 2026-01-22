"""Integration tests for m_insight worker.

Tests the complete mInsight workflow using real services:
- Real database with SQLAlchemy-Continuum versioning
- Real MQTT broker (if configured)
- Entity creation via FastAPI TestClient
- Worker runs as async task (not subprocess for easier testing)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from store.common import database, EntitySyncState, ImageIntelligence
from store.m_insight.media_insight import MediaInsight

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def m_insight_processor_mock(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, str]]:
    """Mock MInsightProcessor.process() to track calls instead of printing.
    
    Returns:
        List of (image_id, md5) tuples for each process() call
    """
    calls: list[tuple[int, str]] = []
    
    original_process = MediaInsight.process
    
    async def mock_process(self: Any, data: Any) -> bool:
        """Mock process that tracks calls and delegates to original for qualification."""
        # Call original to get qualification result
        result = await original_process(self, data)
        if result:
            calls.append((data.id, data.md5))
        return result
    
    monkeypatch.setattr(MediaInsight, "process", mock_process)
    
    return calls


@pytest.fixture
def m_insight_worker(
    clean_data_dir: Path,
    integration_config: Any,
    test_engine: Engine,
) -> MediaInsight:
    """Create MInsightProcessor worker instance for testing.
    
    Note: Does not start the worker - tests control when to run reconciliation.
    Uses the test database engine instead of creating its own.
    """
    from store.m_insight.config import MInsightConfig
    from store.common import database
    from sqlalchemy.orm import sessionmaker
    
    # Create config
    config = MInsightConfig(
        id="test-worker",
        cl_server_dir=clean_data_dir,
        media_storage_dir=clean_data_dir / "media",
        public_key_path=clean_data_dir / "keys" / "public_key.pem",
        mqtt_broker=integration_config.mqtt_server,
        mqtt_port=integration_config.mqtt_port,
        mqtt_topic="test/m_insight",
    )
    
    # Use test database engine instead of initializing a new database
    # This ensures worker uses the same in-memory database as tests
    database.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    # Create worker
    worker = MediaInsight(config=config)
    
    yield worker


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_sync_state(session: Session) -> int:
    """Get current last_version from entity_sync_state."""
    stmt = select(EntitySyncState).where(EntitySyncState.id == 1)
    sync_state = session.execute(stmt).scalar_one_or_none()
    return sync_state.last_version if sync_state else 0


def get_intelligence_count(session: Session) -> int:
    """Get count of rows in image_intelligence table."""
    stmt = select(ImageIntelligence)
    return len(session.execute(stmt).scalars().all())


def get_intelligence_for_image(session: Session, image_id: int) -> ImageIntelligence | None:
    """Get intelligence row for specific image."""
    stmt = select(ImageIntelligence).where(ImageIntelligence.image_id == image_id)
    return session.execute(stmt).scalar_one_or_none()


# ============================================================================
# A. STARTUP TESTS
# ============================================================================



async def test_empty_sync_state_queues_all_images(
    client: TestClient,
    test_images_unique: list[Path],
    m_insight_worker: MediaInsight,
    m_insight_processor_mock: list[tuple[int, str]],
    test_db_session: Session,
) -> None:
    """Test that empty sync state processes all existing images."""
    # Create 3 images via API using 3 different image files
    image_ids = []
    for i, image_path in enumerate(test_images_unique):
        with image_path.open("rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (f"test{i}.png", f, "image/png")},
                data={
                    "label": f"Test Image {i}",
                    "is_collection": "false",
                },
            )
        assert response.status_code == 201, f"Failed to create image {i}: {response.json()}"
        image_ids.append(response.json()["id"])
    
    # Verify sync state is 0 (or doesn't exist yet)
    initial_version = get_sync_state(test_db_session)
    assert initial_version == 0
    
    # Run reconciliation
    processed_count = await m_insight_worker.run_once()
    
    # Verify all 3 images were processed
    assert processed_count == 3
    assert len(m_insight_processor_mock) == 3
    
    # Verify intelligence rows created
    assert get_intelligence_count(test_db_session) == 3
    
    # Verify sync state advanced
    final_version = get_sync_state(test_db_session)
    assert final_version > initial_version



async def test_existing_sync_state_only_newer_versions(
    client: TestClient,
    test_images_unique: list[Path],
    m_insight_worker: MediaInsight,
    m_insight_processor_mock: list[tuple[int, str]],
    test_db_session: Session,
) -> None:
    """Test that existing sync state only processes new images."""
    # Create initial image
    response = client.post(
        "/entities/",
        files={"image": ("test1.png", test_images_unique[0].open("rb"), "image/png")},
        data={"label": "Initial Image", "is_collection": "false"},
    )
    assert response.status_code == 201
    first_id = response.json()["id"]
    
    # Run first reconciliation
    await m_insight_worker.run_once()
    assert len(m_insight_processor_mock) == 1
    first_version = get_sync_state(test_db_session)
    
    # Clear mock calls
    m_insight_processor_mock.clear()
    
    # Create new image (different file)
    response = client.post(
        "/entities/",
        files={"image": ("test2.png", test_images_unique[1].open("rb"), "image/png")},
        data={"label": "New Image", "is_collection": "false"},
    )
    assert response.status_code == 201
    second_id = response.json()["id"]
    
    # Run second reconciliation
    processed_count = await m_insight_worker.run_once()
    
    # Verify only new image was processed
    assert processed_count == 1
    assert len(m_insight_processor_mock) == 1
    assert m_insight_processor_mock[0][0] == second_id
    
    # Verify sync state advanced
    second_version = get_sync_state(test_db_session)
    assert second_version > first_version
    
    # Verify total intelligence rows
    assert get_intelligence_count(test_db_session) == 2


# ============================================================================
# B. UPDATE COALESCING TESTS
# ============================================================================



async def test_multiple_md5_changes_single_queue(
    client: TestClient,
    sample_images: list[Path],
    m_insight_worker: MediaInsight,
    m_insight_processor_mock: list[tuple[int, str]],
    test_db_session: Session,
) -> None:
    """Test that multiple md5 updates result in single processing with latest md5."""
    # Create initial image
    response = client.post(
        "/entities/",
        files={"image": ("test.jpg", sample_images[0].open("rb"), "image/jpeg")},
        data={"label": "Test Image", "is_collection": "false"},
    )
    assert response.status_code == 201
    image_id = response.json()["id"]
    
    # Update with different images (different md5)
    for i in range(1, 3):
        response = client.put(
            f"/entities/{image_id}",
            files={"image": (f"test{i}.jpg", sample_images[i].open("rb"), "image/jpeg")},
            data={"label": "Test Image", "is_collection": "false"},
        )
        assert response.status_code == 200
    
    # Get final md5 from response
    final_md5 = response.json()["md5"]
    
    # Run reconciliation
    processed_count = await m_insight_worker.run_once()
    
    # Verify single processing with latest md5
    assert processed_count == 1
    assert len(m_insight_processor_mock) == 1
    assert m_insight_processor_mock[0] == (image_id, final_md5)
    
    # Verify single intelligence row with latest md5
    intelligence = get_intelligence_for_image(test_db_session, image_id)
    assert intelligence is not None
    assert intelligence.md5 == final_md5
    assert intelligence.status == "queued"



async def test_process_called_once_per_image(
    client: TestClient,
    sample_images: list[Path],
    m_insight_worker: MediaInsight,
    m_insight_processor_mock: list[tuple[int, str]],
    test_db_session: Session,
) -> None:
    """Test that process() is called exactly once per image despite multiple updates."""
    # Create image
    response = client.post(
        "/entities/",
        files={"image": ("test.jpg", sample_images[0].open("rb"), "image/jpeg")},
        data={"label": "Test Image", "is_collection": "false"},
    )
    assert response.status_code == 201
    image_id = response.json()["id"]
    
    # Update 5 times
    for i in range(1, 6):
        client.put(
            f"/entities/{image_id}",
            files={"image": (f"test{i}.jpg", sample_images[i % len(sample_images)].open("rb"), "image/jpeg")},
            data={"label": "Test Image", "is_collection": "false"},
        )
    
    # Run reconciliation
    await m_insight_worker.run_once()
    
    # Verify exactly one process() call
    assert len(m_insight_processor_mock) == 1
    assert m_insight_processor_mock[0][0] == image_id


# ============================================================================
# C. IDEMPOTENCY TESTS
# ============================================================================



async def test_no_duplicate_processing(
    client: TestClient,
    sample_image: Path,
    m_insight_worker: MediaInsight,
    m_insight_processor_mock: list[tuple[int, str]],
    test_db_session: Session,
) -> None:
    """Test that running reconciliation twice doesn't reprocess images."""
    # Create image
    response = client.post(
        "/entities/",
        files={"image": ("test.jpg", sample_image.open("rb"), "image/jpeg")},
        data={"label": "Test Image", "is_collection": "false"},
    )
    assert response.status_code == 201
    image_id = response.json()["id"]
    
    # First reconciliation
    await m_insight_worker.run_once()
    assert len(m_insight_processor_mock) == 1
    
    # Clear mock
    m_insight_processor_mock.clear()
    
    # Second reconciliation (no new changes)
    processed_count = await m_insight_worker.run_once()
    
    # Verify no reprocessing
    assert processed_count == 0
    assert len(m_insight_processor_mock) == 0
    
    # Verify intelligence row unchanged
    assert get_intelligence_count(test_db_session) == 1


# ============================================================================
# D. DELETION TESTS
# ============================================================================



async def test_delete_image_removes_intelligence(
    client: TestClient,
    sample_image: Path,
    m_insight_worker: MediaInsight,
    test_db_session: Session,
) -> None:
    """Test that deleting image cascades to intelligence row."""
    # Create and process image
    response = client.post(
        "/entities/",
        files={"image": ("test.jpg", sample_image.open("rb"), "image/jpeg")},
        data={"label": "Test Image", "is_collection": "false"},
    )
    assert response.status_code == 201
    image_id = response.json()["id"]
    
    await m_insight_worker.run_once()
    
    # Verify intelligence row exists
    assert get_intelligence_for_image(test_db_session, image_id) is not None

    # Soft-delete image first
    from store.store.service import EntityService
    service = EntityService(test_db_session, client.app.state.config)
    service.soft_delete_entity(image_id)

    # Hard delete image
    response = client.delete(f"/entities/{image_id}")
    assert response.status_code == 204
    
    # Verify intelligence row was cascade-deleted
    test_db_session.expire_all()  # Refresh session to see changes
    assert get_intelligence_for_image(test_db_session, image_id) is None



async def test_restart_does_not_reinsert_deleted(
    client: TestClient,
    sample_image: Path,
    m_insight_worker: MediaInsight,
    m_insight_processor_mock: list[tuple[int, str]],
    test_db_session: Session,
) -> None:
    """Test that deleted images are not reprocessed after restart."""
    # Create, process, and delete image
    response = client.post(
        "/entities/",
        files={"image": ("test.jpg", sample_image.open("rb"), "image/jpeg")},
        data={"label": "Test Image", "is_collection": "false"},
    )
    assert response.status_code == 201
    image_id = response.json()["id"]
    
    await m_insight_worker.run_once()
    
    # Soft-delete then hard-delete
    from store.store.service import EntityService
    service = EntityService(test_db_session, client.app.state.config)
    service.soft_delete_entity(image_id)
    client.delete(f"/entities/{image_id}")
    
    # Clear mock
    m_insight_processor_mock.clear()
    
    # Simulate restart: create new worker and reconcile
    new_worker = MediaInsight(config=m_insight_worker.config)
    
    processed_count = await new_worker.run_once()
    
    # Verify deleted image not reprocessed
    assert processed_count == 0
    assert len(m_insight_processor_mock) == 0
    assert get_intelligence_for_image(test_db_session, image_id) is None


# ============================================================================
# F. IGNORE TESTS
# ============================================================================



async def test_non_image_entities_ignored(
    client: TestClient,
    m_insight_worker: MediaInsight,
    m_insight_processor_mock: list[tuple[int, str]],
    test_db_session: Session,
) -> None:
    """Test that non-image entities (collections) are ignored."""
    # Create collection (non-image entity)
    response = client.post(
        "/entities/",
        data={"label": "Test Collection", "is_collection": "true"},
    )
    assert response.status_code == 201
    collection_id = response.json()["id"]
    
    # Run reconciliation
    processed_count = await m_insight_worker.run_once()
    
    # Verify no processing
    assert processed_count == 0
    assert len(m_insight_processor_mock) == 0
    
    # Verify no intelligence row created
    assert get_intelligence_count(test_db_session) == 0
    
    # Verify sync state still advanced (versions were checked)
    assert get_sync_state(test_db_session) > 0
