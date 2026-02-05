"""Health check endpoint tests."""

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel




class HealthCheckResponse(BaseModel):
    """Health check response model."""

    status: str
    service: str
    version: str



pytestmark = pytest.mark.integration


class TestHealthCheck:
    """Test the health check endpoint."""

    def test_root_endpoint_returns_200(self, client: TestClient) -> None:
        """GET / should return 200 OK."""
        response = client.get("/")
        assert response.status_code == 200

    def test_root_endpoint_returns_json(self, client: TestClient) -> None:
        """GET / should return JSON response."""
        response = client.get("/")
        content_type = response.headers.get("content-type")
        assert content_type is not None
        assert "application/json" in content_type

    def test_root_endpoint_contains_status(self, client: TestClient) -> None:
        """GET / response should contain status field."""
        response = client.get("/")
        health = HealthCheckResponse.model_validate(response.json())
        assert health.status == "healthy"

    def test_root_endpoint_contains_service_info(self, client: TestClient) -> None:
        """GET / response should contain service name and version."""
        response = client.get("/")
        health = HealthCheckResponse.model_validate(response.json())
        assert "CoLAN" in health.service
        assert health.version == "v1"
