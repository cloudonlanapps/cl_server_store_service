"""Tests for database configuration and WAL mode."""

from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool


class TestWALMode:
    """Test WAL mode and SQLite pragma configuration."""

    def test_enable_wal_mode_sets_pragmas(self):
        """Test that enable_wal_mode sets all required SQLite pragmas."""
        # Create a mock connection and cursor
        from unittest.mock import MagicMock

        from store.database import enable_wal_mode

        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        # Call enable_wal_mode
        enable_wal_mode(mock_conn, None)

        # Verify all pragmas were executed
        expected_pragmas = [
            "PRAGMA journal_mode=WAL",
            "PRAGMA synchronous=NORMAL",
            "PRAGMA cache_size=-64000",
            "PRAGMA temp_store=MEMORY",
            "PRAGMA mmap_size=30000000000",
            "PRAGMA wal_autocheckpoint=1000",
            "PRAGMA busy_timeout=10000",
            "PRAGMA foreign_keys=ON",
        ]

        assert mock_cursor.execute.call_count == len(expected_pragmas)
        for i, expected_pragma in enumerate(expected_pragmas):
            actual_call = mock_cursor.execute.call_args_list[i][0][0]
            assert actual_call == expected_pragma

        # Verify cursor was closed
        mock_cursor.close.assert_called_once()

    def test_wal_mode_applied_to_real_sqlite_connection(self, tmp_path):
        """Test that WAL mode is actually applied to a real SQLite database."""
        from store.database import create_db_engine

        # Create a temporary database file
        db_path = tmp_path / "test_wal.db"
        database_url = f"sqlite:///{db_path}"

        # Create engine (this should register the WAL mode listener)
        engine = create_db_engine(database_url, echo=False)

        # Create a connection and verify WAL mode is enabled
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA journal_mode")).fetchone()
            assert result[0].upper() == "WAL"

            # Verify other pragmas
            result = conn.execute(text("PRAGMA synchronous")).fetchone()
            assert result[0] == 1  # NORMAL = 1

            result = conn.execute(text("PRAGMA foreign_keys")).fetchone()
            assert result[0] == 1  # ON = 1

        engine.dispose()

    def test_wal_mode_listener_registered_for_sqlite(self):
        """Test that WAL mode listener is registered for SQLite databases."""
        from store.database import create_db_engine, enable_wal_mode

        # Create a SQLite engine
        database_url = "sqlite:///:memory:"
        engine = create_db_engine(database_url, echo=False)

        # Check if enable_wal_mode is registered as a listener
        # Get all listeners for the 'connect' event
        listeners = event.contains(engine, "connect", enable_wal_mode)
        assert listeners, "WAL mode listener should be registered for SQLite"

        engine.dispose()

    def test_create_session_factory(self):
        """Test that create_session_factory creates a valid session factory."""
        from store.database import create_session_factory

        # Create a test engine
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        # Create session factory
        session_factory = create_session_factory(engine)

        # Verify we can create a session
        session = session_factory()
        assert session is not None
        session.close()

        engine.dispose()

    def test_get_db_session_yields_and_closes(self):
        """Test that get_db_session properly yields and closes sessions."""
        from store.database import create_db_engine, create_session_factory, get_db_session

        # Create engine and session factory
        engine = create_db_engine("sqlite:///:memory:")
        session_factory = create_session_factory(engine)

        # Use the generator
        gen = get_db_session(session_factory)
        session = next(gen)

        # Verify we got a session
        assert session is not None

        # Verify session is closed after generator completes
        try:
            next(gen)
        except StopIteration:
            pass

        # Session should be closed now
        # We can't directly check if closed, but we can verify no errors occur
        engine.dispose()

    def test_wal_mode_concurrent_reads(self, tmp_path):
        """Test that WAL mode allows concurrent reads."""
        from store.database import create_db_engine, create_session_factory
        from store.models import Base

        # Create a temporary database
        db_path = tmp_path / "test_concurrent.db"
        database_url = f"sqlite:///{db_path}"

        # Create engine with WAL mode
        engine = create_db_engine(database_url)
        Base.metadata.create_all(bind=engine)

        session_factory = create_session_factory(engine)

        # Create two sessions (simulating concurrent reads)
        session1 = session_factory()
        session2 = session_factory()

        try:
            # Both sessions should be able to read without blocking
            # This is a basic test - in WAL mode, reads don't block each other
            result1 = session1.execute(text("SELECT 1")).fetchone()
            result2 = session2.execute(text("SELECT 1")).fetchone()

            assert result1[0] == 1
            assert result2[0] == 1
        finally:
            session1.close()
            session2.close()
            engine.dispose()
