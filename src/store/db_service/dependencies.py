from store.db_service import DBService

_db_service: DBService | None = None


def get_db_service() -> DBService:
    """Dependency to get DBService instance."""
    global _db_service
    if _db_service is None:
        _db_service = DBService()
    return _db_service
