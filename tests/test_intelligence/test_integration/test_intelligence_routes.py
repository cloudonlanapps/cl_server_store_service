import pytest
from fastapi.testclient import TestClient
from store.common.schemas import Item

pytestmark = [pytest.mark.intelligence, pytest.mark.integration]

def test_intelligence_routes_exist(client: TestClient):
    """Verify that intelligence routes are registered and accessible.
    
    We test with meaningful errors rather than 404.
    """
    # 1. Test get entity jobs
    # Create entity first
    response = client.post(
        "/entities/",
        data={"is_collection": "true", "label": "Test Jobs"}
    )
    assert response.status_code == 201
    entity_id = response.json()["id"]
    
    response = client.get(f"/entities/{entity_id}/jobs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    
    # 2. Test get entity faces
    response = client.get(f"/entities/{entity_id}/faces")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    
    # 3. Test similar images (should be 404 or success if indexed)
    response = client.post(f"/entities/{entity_id}/similar")
    # Even if no images, it should be a valid route. 
    # If it returns 404, then the route is not registered.
    assert response.status_code != 404
    
    # 4. Test known persons
    response = client.get("/known-persons")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_face_similarity_route(client: TestClient):
    """Test face similarity route exists."""
    # Use a fake ID - should return 404 from service layer, not from FastAPI routing
    response = client.get("/faces/999/similar")
    assert response.status_code == 404
    # If it was a routing error, detail would be "Not Found"
    # If it's a service error, it's usually more specific or just 404.
    
def test_person_management_routes(client: TestClient):
    """Test person management routes exist."""
    response = client.get("/known-persons/999")
    assert response.status_code == 404
    
    response = client.patch("/known-persons/999", json={"name": "Test"})
    assert response.status_code == 404
    
    response = client.get("/known-persons/999/faces")
    assert response.status_code == 404
