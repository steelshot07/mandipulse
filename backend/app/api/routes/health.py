"""GET /health."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.schemas.health import HealthResponse
from app.services.health import check_database

router = APIRouter(tags=["health"])


def get_db_checker() -> Callable[[], bool]:
    """Dependency so tests can swap the real database check."""
    return check_database


@router.get("/health", response_model=HealthResponse)
def health(
    response: Response,
    db_checker: Annotated[Callable[[], bool], Depends(get_db_checker)],
) -> HealthResponse:
    """Report API status and whether the database is reachable."""
    if db_checker():
        return HealthResponse(status="ok", db="ok")
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="degraded", db="error")
