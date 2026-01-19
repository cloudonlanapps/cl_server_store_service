"""Singleton ComputeClient with MQTT monitoring for the store service."""

from __future__ import annotations

from cl_client import ComputeClient, ServerConfig, SessionManager
from loguru import logger

from .pysdk_config import PySDKRuntimeConfig

_compute_client: ComputeClient | None = None
_session_manager: SessionManager | None = None
_pysdk_config: PySDKRuntimeConfig | None = None


def get_compute_client() -> ComputeClient:
    """Get the global ComputeClient singleton.

    Must be called after async_get_compute_client() has initialized the client.

    Returns:
        ComputeClient singleton instance with authentication

    Raises:
        RuntimeError: If called before initialization via async_get_compute_client()
    """
    global _compute_client

    if _compute_client is None:
        raise RuntimeError(
            "ComputeClient not initialized. Call async_get_compute_client(config) first "
            + "(typically done in FastAPI startup event)."
        )

    return _compute_client


def get_pysdk_config() -> PySDKRuntimeConfig:
    """Get the stored PySDKRuntimeConfig.

    Returns:
        PySDKRuntimeConfig instance

    Raises:
        RuntimeError: If called before initialization
    """
    global _pysdk_config

    if _pysdk_config is None:
        raise RuntimeError(
            "PySDKRuntimeConfig not initialized. Call async_get_compute_client(config) first."
        )

    return _pysdk_config


async def async_get_compute_client(config: PySDKRuntimeConfig) -> ComputeClient:
    """Get or create the global ComputeClient singleton (async version).

    This is the preferred method to call from async contexts (e.g., FastAPI startup).

    Args:
        config: PySDK runtime configuration

    Returns:
        ComputeClient singleton instance with authentication
    """
    global _compute_client, _session_manager, _pysdk_config

    if _compute_client is None:
        # Store config for later retrieval
        _pysdk_config = config
        # Create server configuration
        server_config = ServerConfig(
            auth_url=config.auth_service_url,
            compute_url=config.compute_service_url,
            mqtt_broker=config.mqtt_broker,
            mqtt_port=config.mqtt_port,
        )

        # Create SessionManager and login
        _session_manager = SessionManager(server_config=server_config)
        _ = await _session_manager.login(
            username=config.compute_username,
            password=config.compute_password,
        )

        # Create ComputeClient via SessionManager (includes JWT auth provider)
        _compute_client = _session_manager.create_compute_client()

        logger.info(
            "Initialized ComputeClient with auth: "
            + f"compute={config.compute_service_url}, "
            + f"user={config.compute_username}, "
            + f"mqtt={config.mqtt_broker}:{config.mqtt_port}"
        )

    return _compute_client


async def shutdown_compute_client() -> None:
    """Shutdown the global ComputeClient singleton.

    Closes both the ComputeClient (httpx session + MQTT) and SessionManager.
    """
    global _compute_client, _session_manager

    if _compute_client:
        await _compute_client.close()
        _compute_client = None
        logger.debug("ComputeClient closed")

    if _session_manager:
        await _session_manager.close()
        _session_manager = None
        logger.debug("SessionManager closed")

    logger.info("ComputeClient shutdown complete")
