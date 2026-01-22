import pytest
from unittest.mock import MagicMock, patch
from store.common import versioning  # Must be first
from store.common.models import Entity, ServiceConfig
from store.m_insight.models import ImageIntelligence, EntitySyncState
from store.m_insight.intelligence.models import Face, KnownPerson, FaceMatch, EntityJob
from store.m_insight.intelligence.retrieve_service import IntelligenceRetrieveService
from store.store.config import StoreConfig
from pathlib import Path
import json
from fastapi.testclient import TestClient
from store.main import create_app

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def mock_config(integration_config):
    return StoreConfig(
        cl_server_dir=Path("/tmp/fake"),
        media_storage_dir=Path("/tmp/fake/media"),
        public_key_path=Path("/tmp/fake/keys/public_key.pem"),
        auth_disabled=True,
        server_port=integration_config.store_port
    )

@pytest.fixture
def retrieve_service(mock_db, mock_config):
    with patch("store.m_insight.intelligence.retrieve_service.get_qdrant_store"), \
         patch("store.m_insight.intelligence.retrieve_service.get_face_store"), \
         patch("store.m_insight.intelligence.retrieve_service.get_dino_store"):
        return IntelligenceRetrieveService(mock_db, mock_config)

@pytest.fixture
def client(mock_db, mock_config):
    app = create_app(mock_config)
    from store.common.database import get_db
    app.dependency_overrides[get_db] = lambda: mock_db
    return TestClient(app)

def test_get_entity_faces(retrieve_service, mock_db):
    """Test retrieval of faces for an entity."""
    mock_face = Face(
        id=1,
        image_id=10,
        bbox=json.dumps({"x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 1.0}),
        landmarks=json.dumps({
            "right_eye": [0.6, 0.4],
            "left_eye": [0.4, 0.4],
            "nose_tip": [0.5, 0.5],
            "mouth_right": [0.6, 0.6],
            "mouth_left": [0.4, 0.6]
        }),
        confidence=0.9,
        file_path="faces/1.jpg",
        created_at=1000
    )
    mock_db.query.return_value.filter.return_value.all.return_value = [mock_face]
    faces = retrieve_service.get_entity_faces(10)
    assert len(faces) == 1
    assert faces[0].id == 1
    assert faces[0].confidence == 0.9

def test_get_entity_jobs(retrieve_service, mock_db):
    """Test retrieval of jobs for an entity."""
    mock_job = EntityJob(
        id=1,
        image_id=10,
        job_id="job123",
        task_type="face_detection",
        status="completed",
        created_at=1000,
        updated_at=1100
    )
    mock_db.query.return_value.filter.return_value.all.return_value = [mock_job]
    jobs = retrieve_service.get_entity_jobs(10)
    assert len(jobs) == 1
    assert jobs[0].job_id == "job123"

def test_search_similar_images(retrieve_service, mock_db):
    """Test CLIP similarity search."""
    retrieve_service.qdrant_store.get_vector.return_value = MagicMock(embedding=[0.1, 0.2])
    retrieve_service.qdrant_store.search.return_value = [
        MagicMock(id=2, score=0.9)
    ]
    
    results = retrieve_service.search_similar_images(1)
    assert len(results) == 1
    assert results[0].image_id == 2
    assert results[0].score == 0.9

def test_search_similar_images_dino(retrieve_service, mock_db):
    """Test DINO similarity search."""
    retrieve_service.dino_store.get_vector.return_value = MagicMock(embedding=[0.3, 0.4])
    retrieve_service.dino_store.search.return_value = [
        MagicMock(id=2, score=0.88)
    ]
    
    response = retrieve_service.search_similar_images_dino(1)
    assert response.query_image_id == 1
    assert len(response.results) == 1
    assert response.results[0].image_id == 2

def test_get_known_person(retrieve_service, mock_db):
    """Test generic known person retrieval."""
    mock_person = KnownPerson(id=5, name="John", created_at=1000, updated_at=1100)
    mock_db.query.return_value.filter.return_value.first.return_value = mock_person
    mock_db.query.return_value.filter.return_value.count.return_value = 2
    
    person = retrieve_service.get_known_person(5)
    assert person.name == "John"
    assert person.face_count == 2

def test_get_all_known_persons(retrieve_service, mock_db):
    """Test listing all known persons."""
    mock_person = KnownPerson(id=1, name="Alice", created_at=1000, updated_at=1100)
    mock_db.query.return_value.all.return_value = [mock_person]
    mock_db.query.return_value.filter.return_value.count.return_value = 1
    
    persons = retrieve_service.get_all_known_persons()
    assert len(persons) == 1
    assert persons[0].name == "Alice"

def test_update_known_person_name(retrieve_service, mock_db):
    """Test name update."""
    person = KnownPerson(id=1, name="Old", created_at=1000, updated_at=1100)
    mock_db.query.return_value.filter.return_value.first.return_value = person
    
    retrieve_service.update_known_person_name(1, "New")
    assert person.name == "New"
    mock_db.commit.assert_called_once()

def test_search_similar_faces_by_id(retrieve_service, mock_db):
    """Test face store similarity search."""
    mock_face = Face(
        id=2,
        image_id=10,
        bbox=json.dumps({"x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 1.0}),
        landmarks=json.dumps({
            "right_eye": [0.6, 0.4],
            "left_eye": [0.4, 0.4],
            "nose_tip": [0.5, 0.5],
            "mouth_right": [0.6, 0.6],
            "mouth_left": [0.4, 0.6]
        }),
        confidence=0.9,
        file_path="x.jpg",
        created_at=1000
    )
    # The service queries Face table for each result
    mock_db.query.return_value.filter.return_value.first.return_value = mock_face
    
    retrieve_service.face_store.get_vector.return_value = MagicMock(embedding=[0.5, 0.6])
    retrieve_service.face_store.search.return_value = [
        MagicMock(id=2, score=0.88, payload={})
    ]
    
    results = retrieve_service.search_similar_faces_by_id(1)
    assert len(results) == 1
    assert results[0].face_id == 2
    assert results[0].score == 0.88

@pytest.mark.asyncio
async def test_search_similar_images_with_details(client, mock_db):
    """Test find_similar_images route with include_details=True."""
    from store.common import models as common_models
    from store.m_insight.intelligence.schemas import SimilarImageResult
    # Use patch to mock IntelligenceRetrieveService and EntityService in the routes module
    with patch("store.m_insight.intelligence.routes.IntelligenceRetrieveService") as mock_service_class, \
         patch("store.store.service.EntityService") as mock_entity_service_class:
        
        # Ensure entity check passes
        mock_entity = MagicMock(spec=common_models.Entity)
        mock_entity.id = 1
        mock_entity.is_collection = False
        mock_db.query.return_value.filter.return_value.first.return_value = mock_entity
        
        mock_service = mock_service_class.return_value
        # MUST use actual schema object or dict because Pydantic validation expects it
        # MagicMock fails validation because from_attributes=True is not invalid on the schema
        mock_result = SimilarImageResult(image_id=2, score=0.9, entity=None)
        mock_service.search_similar_images.return_value = [mock_result]
        
        mock_entity_service = mock_entity_service_class.return_value
        mock_entity_service.get_entity_by_id.return_value = {"id": 2, "label": "Detail"}
        
        response = client.get("/intelligence/entities/1/similar?include_details=true")
        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["entity"]["label"] == "Detail"

@pytest.mark.asyncio
async def test_get_entity_jobs_404(client, mock_db):
    """Test get_entity_jobs route returns 404 when entity missing."""
    mock_db.query.return_value.filter.return_value.first.return_value = None
    response = client.get("/intelligence/entities/999/jobs")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_find_similar_faces_404(client, mock_db):
    """Test find_similar_faces route returns 404 when face missing."""
    mock_db.query.return_value.filter.return_value.first.return_value = None
    response = client.get("/intelligence/faces/999/similar")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_get_face_matches_404(client, mock_db):
    """Test get_face_matches route returns 404 when face missing."""
    mock_db.query.return_value.filter.return_value.first.return_value = None
    response = client.get("/intelligence/faces/999/matches")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_get_known_person_404(client):
    """Test get_known_person route returns 404 when person missing."""
    with patch("store.m_insight.intelligence.routes.IntelligenceRetrieveService") as mock_service_class:
        mock_service = mock_service_class.return_value
        mock_service.get_known_person.return_value = None
        response = client.get("/intelligence/known-persons/999")
        assert response.status_code == 404

@pytest.mark.asyncio
async def test_get_person_faces_404(client, mock_db):
    """Test get_person_faces route returns 404 when person missing."""
    mock_db.query.return_value.filter.return_value.first.return_value = None
    response = client.get("/intelligence/known-persons/999/faces")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_find_similar_images_404(client, mock_db):
    """Test find_similar_images route returns 404 when entity missing."""
    mock_db.query.return_value.filter.return_value.first.return_value = None
    response = client.get("/intelligence/entities/999/similar")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_find_similar_images_no_results(client, mock_db):
    """Test find_similar_images route returns 404 when no results found."""
    mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(id=1)
    with patch("store.m_insight.intelligence.routes.IntelligenceRetrieveService") as mock_service_class:
        mock_service = mock_service_class.return_value
        mock_service.search_similar_images.return_value = []
        response = client.get("/intelligence/entities/1/similar")
        assert response.status_code == 404
        assert "No similar images found" in response.json()["detail"]

@pytest.mark.asyncio
async def test_find_similar_faces_no_results(client, mock_db):
    """Test find_similar_faces route returns 404 when no results found."""
    mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(id=1)
    with patch("store.m_insight.intelligence.routes.IntelligenceRetrieveService") as mock_service_class:
        mock_service = mock_service_class.return_value
        mock_service.search_similar_faces_by_id.return_value = []
        response = client.get("/intelligence/faces/1/similar")
        assert response.status_code == 404
        assert "No similar faces found" in response.json()["detail"]

@pytest.mark.asyncio
async def test_update_person_name_404(client):
    """Test update_person_name route returns 404 when person missing."""
    with patch("store.m_insight.intelligence.routes.IntelligenceRetrieveService") as mock_service_class:
        mock_service = mock_service_class.return_value
        mock_service.update_known_person_name.return_value = None
        response = client.patch("/intelligence/known-persons/999", json={"name": "New"})
        assert response.status_code == 404
