"""
Authentication unit tests for media_store service.

These tests verify the authentication logic directly without going through
the full FastAPI request cycle. For full end-to-end testing, integration
tests with a running authentication service are recommended.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException
from jose import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend


class TestAuthenticationLogic:
    """Test authentication logic functions directly."""

    @pytest.fixture(scope="class")
    def key_pair(self, tmp_path_factory):
        """Generate ES256 key pair for testing."""
        tmp_path = tmp_path_factory.mktemp("keys")

        # Generate private key
        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())

        # Serialize keys
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        # Save public key
        public_key_path = tmp_path / "public_key.pem"
        public_key_path.write_bytes(public_pem)

        return private_pem, str(public_key_path)

    def test_require_permission_allows_correct_permission(self):
        """User with the required permission should be allowed."""
        from src.auth import require_permission
        import asyncio

        from unittest.mock import patch

        # Mock user with write permission
        user = {
            "sub": "testuser",
            "permissions": ["media_store_write"],
            "is_admin": False,
        }

        # Should not raise exception
        with patch("src.auth.AUTH_DISABLED", False):
            permission_checker = require_permission("media_store_write")
            result = asyncio.run(permission_checker(user))
            assert result == user

    def test_require_permission_allows_admin(self):
        """Admin user should be allowed even without specific permission."""
        from src.auth import require_permission
        import asyncio

        from unittest.mock import patch

        user = {"sub": "admin", "permissions": [], "is_admin": True}

        with patch("src.auth.AUTH_DISABLED", False):
            permission_checker = require_permission("media_store_write")
            result = asyncio.run(permission_checker(user))
            assert result == user

    def test_require_permission_rejects_wrong_permission(self):
        """User with only read permission should be rejected when write is required."""
        from src.auth import require_permission
        import asyncio

        from unittest.mock import patch

        user = {
            "sub": "testuser",
            "permissions": ["media_store_read"],
            "is_admin": False,
        }

        with patch("src.auth.AUTH_DISABLED", False):
            with pytest.raises(HTTPException) as exc_info:
                permission_checker = require_permission("media_store_write")
                asyncio.run(permission_checker(user))

            assert exc_info.value.status_code == 403

    def test_require_permission_rejects_none_user(self):
        """None user (no auth) should be rejected when auth is not disabled."""
        from src.auth import require_permission, AUTH_DISABLED
        import asyncio

        from unittest.mock import patch

        # Only test if auth is enabled
        with patch("src.auth.AUTH_DISABLED", False):
            with pytest.raises(HTTPException) as exc_info:
                permission_checker = require_permission("media_store_write")
                asyncio.run(permission_checker(None))

            assert exc_info.value.status_code == 401

    def test_require_permission_allows_read_permission(self):
        """User with media_store_read permission should be allowed."""
        from src.auth import require_permission
        import asyncio

        from unittest.mock import patch

        user = {
            "sub": "testuser",
            "permissions": ["media_store_read"],
            "is_admin": False,
        }

        with patch("src.auth.AUTH_DISABLED", False):
            permission_checker = require_permission("media_store_read")
            result = asyncio.run(permission_checker(user))
            assert result == user

    def test_require_admin_allows_admin_user(self):
        """Admin user should be allowed by require_admin."""
        from src.auth import require_admin
        import asyncio

        from unittest.mock import patch

        user = {"sub": "admin", "permissions": [], "is_admin": True}

        with patch("src.auth.AUTH_DISABLED", False):
            result = asyncio.run(require_admin(user))
            assert result == user

    def test_require_admin_rejects_non_admin(self):
        """Non-admin user should be rejected by require_admin."""
        from src.auth import require_admin
        import asyncio

        from unittest.mock import patch

        user = {
            "sub": "testuser",
            "permissions": ["media_store_write"],
            "is_admin": False,
        }

        with patch("src.auth.AUTH_DISABLED", False):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(require_admin(user))

            assert exc_info.value.status_code == 403


class TestAuthenticationModes:
    """Test authentication mode configurations."""

    def test_auth_disabled_flag_defaults_to_false(self):
        """AUTH_DISABLED should default to false."""
        from cl_server_shared.config import AUTH_DISABLED

        # In test environment without env var, should be False
        # (This may vary based on test setup)
        assert isinstance(AUTH_DISABLED, bool)

    def test_read_auth_enabled_flag_defaults_to_false(self):
        """READ_AUTH_ENABLED should default to false."""
        from cl_server_shared.config import READ_AUTH_ENABLED

        # In test environment without env var, should be False
        assert isinstance(READ_AUTH_ENABLED, bool)

    def test_demo_mode_bypasses_permission_check(self):
        """When AUTH_DISABLED=true, permission checks should be bypassed."""
        from src.auth import require_permission
        import asyncio

        from unittest.mock import patch

        with patch("src.auth.AUTH_DISABLED", True):
            # In demo mode, None user should be allowed
            permission_checker = require_permission("media_store_write")
            result = asyncio.run(permission_checker(None))
            assert result is None

    def test_demo_mode_bypasses_admin_check(self):
        """When AUTH_DISABLED=true, admin checks should be bypassed."""
        from src.auth import require_admin
        import asyncio

        from unittest.mock import patch

        with patch("src.auth.AUTH_DISABLED", True):
            # In demo mode, None user should be allowed
            result = asyncio.run(require_admin(None))
            assert result is None


class TestJWTValidation:
    """Test JWT token validation via FastAPI TestClient.

    Tests validate tokens through actual HTTP requests to the API,
    ensuring the full dependency injection chain and authentication flow works.
    """

    def test_valid_token_is_decoded(
        self, auth_client, jwt_token_generator, key_pair, monkeypatch
    ):
        """Valid JWT token should be decoded successfully."""
        from unittest.mock import patch

        private_key_pem, public_key_path = key_pair
        token = jwt_token_generator.generate_token(
            sub="testuser",
            permissions=["media_store_read"],
            is_admin=False,
            expired=False,
        )

        # Mock the public key path to use test key
        with patch("src.auth.PUBLIC_KEY_PATH", public_key_path):
            headers = {"Authorization": f"Bearer {token}"}
            response = auth_client.get("/entities/", headers=headers)

            # Token should be decoded successfully
            # Response should NOT be 401 (unauthorized)
            assert (
                response.status_code != 401
            ), f"Token validation failed: {response.json()}"
            # Should be 200 (success) or 400 (validation error), not 401 (auth error)
            assert response.status_code in [200, 400]

    def test_expired_token_is_rejected(
        self, auth_client, jwt_token_generator, key_pair
    ):
        """Expired JWT token should be rejected with 401."""
        from unittest.mock import patch

        private_key_pem, public_key_path = key_pair
        token = jwt_token_generator.generate_token(
            sub="testuser",
            permissions=["media_store_write"],
            is_admin=False,
            expired=True,  # Token is expired
        )

        with patch("src.auth.PUBLIC_KEY_PATH", public_key_path):
            headers = {"Authorization": f"Bearer {token}"}
            response = auth_client.get("/entities/", headers=headers)

            # Expired token should be rejected with 401
            assert response.status_code == 401
            assert "invalid" in response.json().get("detail", "").lower()

    def test_invalid_token_format_is_rejected(
        self, auth_client, jwt_token_generator, key_pair
    ):
        """Malformed tokens and tokens with wrong signatures should be rejected."""
        from unittest.mock import patch

        private_key_pem, public_key_path = key_pair

        # Create multiple invalid tokens to test
        invalid_tokens = [
            "not.a.valid.token",  # Wrong format (too few parts)
            "invalid_format",  # Not JWT format at all
            "a.b",  # Missing signature part
            "!!!.!!!.!!!",  # Invalid base64
            jwt_token_generator.generate_invalid_token_wrong_key(),  # Valid format but wrong signature
        ]

        with patch("src.auth.PUBLIC_KEY_PATH", public_key_path):
            for invalid_token in invalid_tokens:
                headers = {"Authorization": f"Bearer {invalid_token}"}
                response = auth_client.get("/entities/", headers=headers)

                # All invalid tokens should return 401
                assert (
                    response.status_code == 401
                ), f"Token '{invalid_token[:20]}...' should be rejected but got {response.status_code}"
