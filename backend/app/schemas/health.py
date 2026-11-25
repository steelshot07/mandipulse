"""Response models for /health."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Service and database status."""

    status: Literal["ok", "degraded"]
    db: Literal["ok", "error"]
