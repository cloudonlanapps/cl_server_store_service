"""
Configuration service for managing runtime settings.

Provides database-backed configuration with in-memory caching for performance.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from .models import ServiceConfig


class ConfigService:
    """Service for managing runtime configuration."""
    
    # Simple in-memory cache
    _cache = {}
    _cache_ttl = 60  # seconds
    _cache_timestamps = {}
    
    def __init__(self, db: Session):
        """Initialize config service.
        
        Args:
            db: SQLAlchemy database session
        """
        self.db = db
    
    @staticmethod
    def _now_timestamp() -> int:
        """Return current UTC timestamp in milliseconds."""
        return int(datetime.now(timezone.utc).timestamp() * 1000)
    
    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached value is still valid.
        
        Args:
            key: Configuration key
            
        Returns:
            True if cache is valid, False otherwise
        """
        if key not in self._cache_timestamps:
            return False
        
        age = (self._now_timestamp() - self._cache_timestamps[key]) / 1000
        return age < self._cache_ttl
    
    def get_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get configuration value.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        # Check cache first
        if self._is_cache_valid(key):
            return self._cache.get(key)
        
        # Query database
        config = self.db.query(ServiceConfig).filter(ServiceConfig.key == key).first()
        
        if config:
            # Update cache
            self._cache[key] = config.value
            self._cache_timestamps[key] = self._now_timestamp()
            return config.value
        
        return default
    
    def set_config(self, key: str, value: str, user_id: Optional[str] = None) -> None:
        """Set configuration value.
        
        Args:
            key: Configuration key
            value: Configuration value
            user_id: User ID making the change
        """
        now = self._now_timestamp()
        
        # Check if config exists
        config = self.db.query(ServiceConfig).filter(ServiceConfig.key == key).first()
        
        if config:
            # Update existing
            config.value = value
            config.updated_at = now
            config.updated_by = user_id
        else:
            # Create new
            config = ServiceConfig(
                key=key,
                value=value,
                updated_at=now,
                updated_by=user_id
            )
            self.db.add(config)
        
        self.db.commit()
        
        # Update cache
        self._cache[key] = value
        self._cache_timestamps[key] = now
    
    def get_read_auth_enabled(self) -> bool:
        """Get read authentication enabled status.
        
        Returns:
            True if read auth is enabled, False otherwise
        """
        value = self.get_config('read_auth_enabled', 'false')
        return value.lower() == 'true'
    
    def set_read_auth_enabled(self, enabled: bool, user_id: Optional[str] = None) -> None:
        """Set read authentication enabled status.
        
        Args:
            enabled: Whether to enable read authentication
            user_id: User ID making the change
        """
        self.set_config('read_auth_enabled', str(enabled).lower(), user_id)
    
    def get_config_metadata(self, key: str) -> Optional[dict]:
        """Get configuration with metadata.
        
        Args:
            key: Configuration key
            
        Returns:
            Dictionary with value, updated_at, updated_by or None
        """
        config = self.db.query(ServiceConfig).filter(ServiceConfig.key == key).first()
        
        if config:
            return {
                "key": config.key,
                "value": config.value,
                "updated_at": config.updated_at,
                "updated_by": config.updated_by
            }
        
        return None
