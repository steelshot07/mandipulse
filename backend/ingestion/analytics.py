"""Refresh the materialized cleaning views after new price data lands."""

from sqlalchemy import Connection, text

from app.core.logging import get_logger

logger = get_logger(__name__)

# Order matters: v_prices_weekly is built from v_prices_clean.
MATERIALIZED_VIEWS = ("v_prices_clean", "v_prices_weekly")


def refresh_price_views(conn: Connection) -> None:
    """Rebuild cleaned and weekly prices. CONCURRENTLY keeps them readable during refresh."""
    for view in MATERIALIZED_VIEWS:
        conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}"))
    logger.info("Refreshed %s", ", ".join(MATERIALIZED_VIEWS))
