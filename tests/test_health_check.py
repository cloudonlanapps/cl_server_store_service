"""Health check endpoint tests."""

import pytest


class TestHealthCheck:
    """Test the health check endpoint."""

    def test_root_endpoint_returns_200(self, client):
        """GET / should return 200 OK."""
        response = client.get("/")
        assert response.status_code == 200

    def test_root_endpoint_returns_json(self, client):
        """GET / should return JSON response."""
        response = client.get("/")
        assert response.headers.get("content-type") is not None
        assert "application/json" in response.headers.get("content-type", "")

    def test_root_endpoint_contains_status(self, client):
        """GET / response should contain status field."""
        response = client.get("/")
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"

    def test_root_endpoint_contains_service_info(self, client):
        """GET / response should contain service name and version."""
        response = client.get("/")
        data = response.json()
        assert "service" in data
        assert "CoLAN" in data["service"]
        assert "version" in data
        assert data["version"] == "v1"
