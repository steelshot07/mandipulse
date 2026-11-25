"""Health checks used by the /health route."""

from sqlalchemy import text

from app.core.logging import get_logger
from app.db.session import get_engine

logger = get_logger(__name__)


def check_database() -> bool:
    """Return True if the database answers ``SELECT 1``."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # any failure means "db not ok"; details go to logs, never the response
        logger.exception("Database health check failed")
        return False
