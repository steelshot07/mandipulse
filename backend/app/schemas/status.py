"""Response models for /status/ingestion."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class IngestionRunOut(BaseModel):
    """One ingestion run. Error text stays server-side (Rules.md §6), only the status is shown."""

    id: int
    job: str
    status: Literal["running", "success", "failed"]
    started_at: datetime
    finished_at: datetime | None
    rows_fetched: int
    rows_inserted: int
    rows_quarantined: int


class SeriesFreshness(BaseModel):
    """How recent the latest price is for one market x commodity series."""

    commodity: str
    market: str
    market_name: str
    last_arrival_date: date | None
    days_since: int | None
    stale: bool


class IngestionStatusResponse(BaseModel):
    last_success_at: datetime | None
    stale_after_days: int
    runs: list[IngestionRunOut]
    series: list[SeriesFreshness]
