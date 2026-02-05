from datetime import datetime
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from store.db_service.db_internals import models
from store.db_service import EntityIntelligenceData, JobInfo



@pytest.mark.usefixtures("qdrant_service", "compute_service", "auth_service")

pytestmark = pytest.mark.integration
class TestIntelligenceRoutes:
    def test_get_entity_faces_not_found(self, client: TestClient):
        """Test getting faces for a non-existent entity returns 404."""
        response = client.get("/intelligence/entities/999999/faces")
        assert response.status_code == 404
        assert response.json()["detail"] == "Entity not found"

    def test_get_entity_jobs_not_found(self, client: TestClient):
        """Test getting jobs for a non-existent entity returns 404."""
        response = client.get("/intelligence/entities/999999/jobs")
        assert response.status_code == 404
        assert response.json()["detail"] == "Entity not found"

    def test_get_all_known_persons_empty(self, client: TestClient):
        """Test getting all known persons when none exist returns empty list."""
        response = client.get("/intelligence/known-persons")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_known_person_not_found(self, client: TestClient):
        """Test getting a non-existent known person returns 404."""
        response = client.get("/intelligence/known-persons/999999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Known person not found"

    def test_get_person_faces_not_found(self, client: TestClient):
        """Test getting faces for a non-existent person returns 404."""
        response = client.get("/intelligence/known-persons/999999/faces")
        assert response.status_code == 404
        assert response.json()["detail"] == "Known person not found"

    def test_update_person_name_not_found(self, client: TestClient):
        """Test updating name for a non-existent person returns 404."""
        response = client.patch(
            "/intelligence/known-persons/999999",
            json={"name": "New Name"}
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Known person not found"

    def test_download_face_embedding_not_found(self, client: TestClient):
        """Test downloading embedding for a non-existent face returns 404."""
        response = client.get("/intelligence/faces/999999/embedding")
        assert response.status_code == 404
        assert response.json()["detail"] == "Face not found"

    def test_download_entity_embedding_not_found(self, client: TestClient):
        """Test downloading embedding for a non-existent entity returns 404."""
        response = client.get("/intelligence/entities/999999/clip_embedding")
        assert response.status_code == 404
        assert response.json()["detail"] == "Entity not found"

    def test_download_entity_dino_embedding_not_found(self, client: TestClient):
        """Test downloading DINO embedding for a non-existent entity returns 404."""
        response = client.get("/intelligence/entities/999999/dino_embedding")
        assert response.status_code == 404
        assert response.json()["detail"] == "Entity not found"



    def test_get_entity_faces_success(self, client: TestClient, test_db_session: Session):
        """Test getting faces for an entity with data."""
        # Create entity
        entity = models.Entity(
            is_collection=False,
            label="test_image.jpg",
            md5="abc123face",
        )
        test_db_session.add(entity)
        test_db_session.commit()

        # Add face
        # Note: bbox is BBox model as JSON string
        face = models.Face(
            entity_id=entity.id,
            bbox='{"x1": 0.1, "y1": 0.1, "x2": 0.5, "y2": 0.5}',
            confidence=0.95,
            landmarks='{"right_eye": [0.2, 0.2], "left_eye": [0.4, 0.2], "nose_tip": [0.3, 0.3], "mouth_right": [0.2, 0.4], "mouth_left": [0.4, 0.4]}',
            file_path="/tmp/face.jpg",
            created_at=int(datetime.now().timestamp() * 1000)
        )
        test_db_session.add(face)
        test_db_session.commit()

        response = client.get(f"/intelligence/entities/{entity.id}/faces")
        assert response.status_code == 200
        faces = response.json()
        assert len(faces) == 1
        assert faces[0]["confidence"] == 0.95

    def test_get_entity_jobs_success(self, client: TestClient, test_db_session: Session):
        """Test getting jobs for an entity with data."""
        # Create entity with intelligence data
        now = int(datetime.now().timestamp() * 1000)
        
        intel_data = EntityIntelligenceData(
            last_updated=now,
            active_jobs=[
                JobInfo(
                    job_id="job_abc_123",
                    task_type="face_detection",
                    started_at=now
                )
            ]
        )
        
        entity = models.Entity(
            is_collection=False,
            label="job_test.jpg",
            md5="job12345"
        )
        test_db_session.add(entity)
        test_db_session.flush()

        # Add intelligence data
        intel = models.EntityIntelligence(
            entity_id=entity.id,
            intelligence_data=intel_data.model_dump()
        )
        test_db_session.add(intel)
        test_db_session.commit()

        response = client.get(f"/intelligence/entities/{entity.id}/jobs")
        assert response.status_code == 200
        jobs = response.json()
        assert len(jobs) == 1
        assert jobs[0]["task_type"] == "face_detection"
        assert jobs[0]["job_id"] == "job_abc_123"

    def test_known_persons_operations(self, client: TestClient, test_db_session: Session):
        """Test creating and updating known persons."""
        # 1. Create a person
        now_ms = int(datetime.now().timestamp() * 1000)
        person = models.KnownPerson(
            name="John Doe",
            created_at=now_ms,
            updated_at=now_ms
        )
        test_db_session.add(person)
        test_db_session.commit()

        # 2. Get all persons
        response = client.get("/intelligence/known-persons")
        assert response.status_code == 200
        persons = response.json()
        assert any(p["id"] == person.id for p in persons)

        # 3. Get specific person
        response = client.get(f"/intelligence/known-persons/{person.id}")
        assert response.status_code == 200
        assert response.json()["name"] == "John Doe"

        # 4. Update person name
        response = client.patch(
            f"/intelligence/known-persons/{person.id}",
            json={"name": "Jane Doe"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Jane Doe"

        # Verify in DB
        test_db_session.refresh(person)
        assert person.name == "Jane Doe"
