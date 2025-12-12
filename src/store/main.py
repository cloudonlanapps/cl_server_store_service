# src/store/main.py
from __future__ import annotations
import os
import sys
import argparse
from pathlib import Path
import logging

logger = logging.getLogger("store")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def run_alembic_migrations(project_root: Path) -> bool:
    """
    Run alembic upgrade head programmatically.
    Returns True on success, False on failure (but does not exit the process).
    """
    try:
        from alembic.config import Config
        from alembic import command
    except Exception as exc:
        logger.warning("Alembic not available: %s", exc)
        return False

    alembic_ini = project_root / "alembic.ini"
    if not alembic_ini.exists():
        logger.info("No alembic.ini found at %s — skipping migrations", alembic_ini)
        return True

    cfg = Config(str(alembic_ini))

    # If your alembic.ini does not contain correct script_location, set it:
    # cfg.set_main_option("script_location", str(project_root / "alembic"))

    logger.info("Running alembic migrations (upgrade head) using %s", alembic_ini)
    try:
        command.upgrade(cfg, "head")
        logger.info("Alembic migrations completed")
        return True
    except Exception as exc:
        logger.error("Alembic migrations failed: %s", exc)
        return False


def start_uvicorn(app, host: str, port: int, reload: bool = False):
    import uvicorn

    if reload:
        # Pass app as import string for reload to work
        uvicorn.run("store:app", host=host, port=port, reload=reload)
    else:
        uvicorn.run(app, host=host, port=port, reload=reload)


def main(argv: list[str] | None = None) -> int:
    """
    Entry point used by poetry script:
      [tool.poetry.scripts]
      store = "store.main:cli"
    """
    parser = argparse.ArgumentParser(prog="store")
    parser.add_argument("--no-auth", action="store_true", help="Disable authentication")
    parser.add_argument(
        "--no-migrate", action="store_true", help="Skip running DB migrations"
    )
    parser.add_argument(
        "--port", "-p", type=int, default=int(os.getenv("PORT", "8001"))
    )
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument(
        "--reload", action="store_true", help="Enable uvicorn reload (dev)"
    )
    args = parser.parse_args(argv)

    # Set env vars expected by your app
    if args.no_auth:
        os.environ["AUTH_DISABLED"] = "true"
    os.environ.setdefault("CL_SERVER_DIR", os.getenv("CL_SERVER_DIR", ""))

    # Determine project root from this file (src/store/main.py -> project root)
    project_root = Path(__file__).resolve().parents[2]

    # Run migrations unless skipped
    if not args.no_migrate:
        ok = run_alembic_migrations(project_root)
        if not ok:
            # You can choose to exit here if migrations are critical:
            logger.warning("Continuing to start even though migrations failed.")
            # return 1   # uncomment to abort on migration failure

    # Import your FastAPI app (adjust the import if your app object is elsewhere)
    try:
        from store import app  # adjust if your app module is different
    except Exception as exc:
        logger.error("Failed to import app: %s", exc)
        return 1

    # Start server (blocks)
    start_uvicorn(app, host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
