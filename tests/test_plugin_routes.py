"""
Tests for cl_ml_tools plugin routes integration.

These tests verify that plugins are discovered and mounted correctly.
For individual plugin tests, see:
- test_plugin_image_resize.py
- test_plugin_image_conversion.py
"""

import pytest


class TestPluginDiscovery:
    """Test that plugins are discovered and mounted correctly."""

    def test_image_resize_route_exists(self, client):
        """Test that image_resize plugin route is mounted."""
        response = client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        paths = schema.get("paths", {})

        assert "/compute/jobs/image_resize" in paths
        assert "post" in paths["/compute/jobs/image_resize"]

    def test_image_conversion_route_exists(self, client):
        """Test that image_conversion plugin route is mounted."""
        response = client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        paths = schema.get("paths", {})

        assert "/compute/jobs/image_conversion" in paths
        assert "post" in paths["/compute/jobs/image_conversion"]

    def test_plugin_routes_have_correct_tags(self, client):
        """Test that plugin routes are tagged correctly."""
        response = client.get("/openapi.json")
        schema = response.json()
        paths = schema.get("paths", {})

        # Check that plugin routes have appropriate tags
        if "/compute/jobs/image_resize" in paths:
            tags = paths["/compute/jobs/image_resize"]["post"].get("tags", [])
            assert len(tags) > 0  # Should have at least one tag

        if "/compute/jobs/image_conversion" in paths:
            tags = paths["/compute/jobs/image_conversion"]["post"].get("tags", [])
            assert len(tags) > 0

    def test_job_management_routes_exist(self, client):
        """Test that job management routes (GET, DELETE) exist."""
        response = client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        paths = schema.get("paths", {})

        # Check job management endpoints
        assert "/compute/jobs/{job_id}" in paths
        job_path = paths["/compute/jobs/{job_id}"]

        assert "get" in job_path, "GET /compute/jobs/{job_id} should exist"
        assert "delete" in job_path, "DELETE /compute/jobs/{job_id} should exist"
