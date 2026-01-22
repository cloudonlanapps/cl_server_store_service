from __future__ import annotations

from ..common.config import BaseConfig


class StoreConfig(BaseConfig):
    """Unified Store service configuration and CLI arguments."""

    # CLI Fields (mapped from argparse)
    host: str = "0.0.0.0"
    port: int = 8001
    debug: bool = False
    reload: bool = False
    log_level: str = "info"
    no_migrate: bool = False

    def finalize(self):
        """Finalize configuration after CLI parsing."""
        self.finalize_base()
