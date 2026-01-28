from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy.orm import Session

from .base import BaseDBService, timed, with_retry
from .db_internals import ServiceConfig, database
from .schemas import ServiceConfigSchema


class ConfigDBService(BaseDBService[ServiceConfigSchema]):
    """Service for managing runtime configuration with caching."""

    model_class = ServiceConfig
    schema_class = ServiceConfigSchema

    # Simple in-memory cache (shared across all instances via class variables)
    _cache: ClassVar[dict[str, str]] = {}
    _cache_ttl: ClassVar[int] = 60  # seconds
    _cache_timestamps: ClassVar[dict[str, int]] = {}

    @staticmethod
    def _now_timestamp() -> int:
        """Return current UTC timestamp in milliseconds."""
        return int(datetime.now(UTC).timestamp() * 1000)

    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached value is still valid."""
        if key not in self._cache_timestamps:
            return False

        age = (self._now_timestamp() - self._cache_timestamps[key]) / 1000
        return age < self._cache_ttl

    @timed
    @with_retry(max_retries=10)
    def get_config(self, key: str, default: str | None = None) -> str | None:
        """Get configuration value with fallback and caching."""
        # Check cache first
        if self._is_cache_valid(key):
            return self._cache.get(key)

        db = self.db if self.db else database.SessionLocal()
        should_close = self.db is None
        try:
            config = db.query(ServiceConfig).filter(ServiceConfig.key == key).first()

            if config:
                # Update cache
                self._cache[key] = config.value
                self._cache_timestamps[key] = self._now_timestamp()
                return config.value

            return default
        finally:
            if should_close:
                db.close()

    @timed
    @with_retry(max_retries=10)
    def set_config(self, key: str, value: str, user_id: str | None = None) -> None:
        """Set configuration value and update cache."""
        now = self._now_timestamp()
        db = self.db if self.db else database.SessionLocal()
        should_close = self.db is None
        try:
            # Check if config exists
            config = db.query(ServiceConfig).filter(ServiceConfig.key == key).first()

            if config:
                # Update existing
                config.value = value
                config.updated_at = now
                config.updated_by = user_id
            else:
                # Create new
                config = ServiceConfig(key=key, value=value, updated_at=now, updated_by=user_id)
                db.add(config)

            db.commit()

            # Update cache
            self._cache[key] = value
            self._cache_timestamps[key] = now
        except Exception:
            db.rollback()
            raise
        finally:
            if should_close:
                db.close()

    def get_read_auth_enabled(self) -> bool:
        """Get read authentication enabled status."""
        value = self.get_config("read_auth_enabled", "false")
        return value.lower() == "true" if value else False

    def set_read_auth_enabled(self, enabled: bool, user_id: str | None = None) -> None:
        """Set read authentication enabled status."""
        self.set_config("read_auth_enabled", str(enabled).lower(), user_id)

    @timed
    @with_retry(max_retries=10)
    def get_config_metadata(self, key: str) -> dict[str, str | int | None] | None:
        """Get configuration with metadata."""
        db = self.db if self.db else database.SessionLocal()
        should_close = self.db is None
        try:
            config = db.query(ServiceConfig).filter(ServiceConfig.key == key).first()

            if config:
                return {
                    "key": config.key,
                    "value": config.value,
                    "updated_at": config.updated_at,
                    "updated_by": config.updated_by,
                }

            return None
        finally:
            if should_close:
                db.close()
