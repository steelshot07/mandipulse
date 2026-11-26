"""GET /status/ingestion: public, read-only, rate-limited by the global limiter."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.time import today_ist
from app.db.session import get_session
from app.schemas.status import IngestionStatusResponse
from app.services.status import get_ingestion_status

router = APIRouter(prefix="/status", tags=["status"])

StatusProvider = Callable[[], IngestionStatusResponse]


def get_status_provider(session: Annotated[Session, Depends(get_session)]) -> StatusProvider:
    """Dependency so tests can swap the database-backed status for a fake."""
    return lambda: get_ingestion_status(session, today_ist())


@router.get("/ingestion", response_model=IngestionStatusResponse)
def ingestion_status(
    response: Response,
    provider: Annotated[StatusProvider, Depends(get_status_provider)],
) -> IngestionStatusResponse:
    """Last 14 ingestion runs and how fresh each market x commodity series is."""
    # Data changes at most a few times a day, so let browsers/CDNs cache briefly.
    response.headers["Cache-Control"] = "public, max-age=300"
    return provider()
