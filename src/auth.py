from __future__ import annotations

import os
import time
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from cl_server_shared.config import PUBLIC_KEY_PATH, AUTH_DISABLED, READ_AUTH_ENABLED
from .database import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token", auto_error=False)

# Cache public key with retry logic
_public_key_cache: Optional[str] = None
_public_key_load_attempts: int = 0
_max_load_attempts: int = 30  # Try for up to 30 seconds


def get_public_key() -> str:
    """Load the public key from file with caching and retry logic.

    Waits for the public key file to be created by the authentication service.
    Returns the cached public key on subsequent calls.
    Raises HTTPException if key cannot be loaded.
    """
    global _public_key_cache, _public_key_load_attempts

    # Return cached key if available
    if _public_key_cache:
        return _public_key_cache

    # Try to load the key
    retry_count = 0
    while retry_count < _max_load_attempts:
        if os.path.exists(PUBLIC_KEY_PATH):
            try:
                with open(PUBLIC_KEY_PATH, "r") as f:
                    _public_key_cache = f.read()
                    if _public_key_cache:
                        return _public_key_cache
            except IOError as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to read public key file: {str(e)}",
                )

        # Key file not found yet, wait and retry (up to 30 seconds for service startup)
        retry_count += 1
        if retry_count < _max_load_attempts:
            time.sleep(1)
        else:
            break

    # If we get here, public key still doesn't exist
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Public key not found at {PUBLIC_KEY_PATH}. Is the authentication service running?",
    )


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
) -> Optional[dict]:
    """Validate the JWT and return the user payload.

    Returns None if AUTH_DISABLED is True (demo mode).
    Returns None if token is not provided and auto_error is False.
    """
    # Demo mode: bypass authentication
    if AUTH_DISABLED:
        return None

    # No token provided
    if token is None:
        return None

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # This will raise HTTPException with detailed message if key can't be loaded
    public_key = get_public_key()

    try:
        payload = jwt.decode(token, public_key, algorithms=["ES256"])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception

        # Debug: Log the payload to understand what claims are in the token
        print(f"DEBUG: JWT Payload = {payload}")
        print(f"DEBUG: is_admin in payload = {'is_admin' in payload}")
        print(f"DEBUG: is_admin value = {payload.get('is_admin')}")

        # Ensure required fields are present in token
        if "is_admin" not in payload:
            # Token missing is_admin field - set default
            payload["is_admin"] = False

        print(f"DEBUG: Final payload is_admin = {payload.get('is_admin')}")
        return payload
    except JWTError as e:
        # Provide more detailed error for debugging
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_permission(permission: str):
    """Dependency to require a specific permission.

    Supports all permission types: media_store_read, media_store_write, ai_inference_support, admin.
    Checks if user has the required permission or admin status.
    In demo mode (AUTH_DISABLED=True), always allows access.
    For media_store_read permission, checks runtime configuration to allow bypass when read auth is disabled.

    Usage:
        @app.get("/protected")
        async def protected_endpoint(user: dict = Depends(require_permission("ai_inference_support"))):
            return {"message": f"Hello {user.get('sub')}"}
    """

    async def permission_checker(
        current_user: Optional[dict] = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> Optional[dict]:
        # Demo mode: bypass permission check
        if AUTH_DISABLED:
            return current_user

        # Check runtime read auth configuration for read permissions
        if permission == "media_store_read":
            from .config_service import ConfigService

            config_service = ConfigService(db)
            read_auth_enabled = config_service.get_read_auth_enabled()

            # If read auth is disabled, allow access without authentication
            if not read_auth_enabled:
                return current_user

        # No user provided but auth is required
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Admin users bypass permission checks
        if current_user.get("is_admin"):
            return current_user

        # Check if user has the required permission
        user_permissions = current_user.get("permissions", [])
        if permission not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {permission}",
            )

        return current_user

    return permission_checker


async def require_admin(
    current_user: Optional[dict] = Depends(get_current_user),
) -> Optional[dict]:
    # Demo mode: bypass permission check
    if AUTH_DISABLED:
        return current_user

    # No user provided but auth is required
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Admin users bypass permission checks
    if not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. admin access required",
        )

    return current_user
