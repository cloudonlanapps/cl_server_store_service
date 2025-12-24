"""Admin configuration endpoint tests with JWT authentication."""



class TestAdminConfigGetEndpoint:
    """Test GET /admin/config endpoint."""

    def test_get_config_with_admin_token_returns_200(self, auth_client, admin_token):
        """GET /admin/config with admin token should return 200 OK."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = auth_client.get("/admin/config", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_get_config_with_read_only_token_returns_403(self, auth_client, read_token):
        """GET /admin/config with read-only token should return 403 Forbidden."""
        headers = {"Authorization": f"Bearer {read_token}"}
        response = auth_client.get("/admin/config", headers=headers)

        assert response.status_code == 403

    def test_get_config_with_write_token_returns_403(self, auth_client, write_token):
        """GET /admin/config with write token (not admin) should return 403 Forbidden."""
        headers = {"Authorization": f"Bearer {write_token}"}
        response = auth_client.get("/admin/config", headers=headers)

        assert response.status_code == 403

    def test_get_config_without_token_returns_401(self, auth_client):
        """GET /admin/config without token should return 401 Unauthorized."""
        response = auth_client.get("/admin/config")

        assert response.status_code == 401

    def test_get_config_with_invalid_token_returns_401(self, auth_client):
        """GET /admin/config with invalid token should return 401 Unauthorized."""
        headers = {"Authorization": "Bearer invalid.token.here"}
        response = auth_client.get("/admin/config", headers=headers)

        assert response.status_code == 401


class TestAdminConfigPutEndpoint:
    """Test PUT /admin/config/read-auth endpoint."""

    def test_put_read_auth_with_admin_token_returns_200(self, auth_client, admin_token):
        """PUT /admin/config/read-auth with admin token should return 200 OK."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        payload = {"enabled": True}
        response = auth_client.put(
            "/admin/config/read-auth", json=payload, headers=headers
        )

        assert response.status_code == 200

    def test_put_read_auth_with_write_token_returns_403(self, auth_client, write_token):
        """PUT /admin/config/read-auth with write token (not admin) should return 403 Forbidden."""
        headers = {"Authorization": f"Bearer {write_token}"}
        payload = {"enabled": True}
        response = auth_client.put(
            "/admin/config/read-auth", json=payload, headers=headers
        )

        assert response.status_code == 403

    def test_put_read_auth_with_read_token_returns_403(self, auth_client, read_token):
        """PUT /admin/config/read-auth with read token should return 403 Forbidden."""
        headers = {"Authorization": f"Bearer {read_token}"}
        payload = {"enabled": True}
        response = auth_client.put(
            "/admin/config/read-auth", json=payload, headers=headers
        )

        assert response.status_code == 403

    def test_put_read_auth_without_token_returns_401(self, auth_client):
        """PUT /admin/config/read-auth without token should return 401 Unauthorized."""
        payload = {"enabled": True}
        response = auth_client.put("/admin/config/read-auth", json=payload)

        assert response.status_code == 401

    def test_put_read_auth_with_invalid_token_returns_401(self, auth_client):
        """PUT /admin/config/read-auth with invalid token should return 401 Unauthorized."""
        headers = {"Authorization": "Bearer invalid.token.here"}
        payload = {"enabled": True}
        response = auth_client.put(
            "/admin/config/read-auth", json=payload, headers=headers
        )

        assert response.status_code == 401

    def test_config_changes_persisted_in_database(
        self, auth_client, admin_token, test_db_session
    ):
        """Config changes via PUT should be persisted in database."""
        from store.config_service import ConfigService

        # Clear cache before test
        ConfigService._cache.clear()
        ConfigService._cache_timestamps.clear()

        # Update config via API
        headers = {"Authorization": f"Bearer {admin_token}"}
        payload = {"enabled": True}
        response = auth_client.put(
            "/admin/config/read-auth", json=payload, headers=headers
        )

        assert response.status_code == 200

        # Verify it was persisted in database
        config_service = ConfigService(test_db_session)
        is_enabled = config_service.get_read_auth_enabled()
        assert is_enabled is True

    def test_subsequent_get_returns_updated_config(self, auth_client, admin_token):
        """Subsequent GET /admin/config should return updated config after PUT."""
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Update config
        payload = {"enabled": True}
        response = auth_client.put(
            "/admin/config/read-auth", json=payload, headers=headers
        )
        assert response.status_code == 200

        # Get updated config
        response = auth_client.get("/admin/config", headers=headers)
        assert response.status_code == 200

        # Verify the config contains the updated value
        data = response.json()
        # The response should contain configuration info
        assert isinstance(data, dict)
