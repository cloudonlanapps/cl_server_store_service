
from dataclasses import dataclass
from pathlib import Path
from ..common.utils import ensure_cl_server_dir


@dataclass
class StoreConfig:
    """Store service configuration."""

    cl_server_dir: Path
    
    media_storage_dir: Path
    public_key_path: Path
    auth_disabled: bool

    @classmethod
    def from_cli_args(cls, args) -> "StoreConfig":
        """Create config from CLI arguments and environment."""
        cl_dir =  ensure_cl_server_dir(create_if_missing=True)
        
        return cls(
            cl_server_dir=cl_dir,
            media_storage_dir=cl_dir / "media",
            public_key_path=cl_dir / "keys" / "public_key.pem",
            auth_disabled=args.no_auth,
        )
