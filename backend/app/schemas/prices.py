"""Response models for /prices."""

from datetime import date
from typing import Literal

from pydantic import BaseModel


class PricePoint(BaseModel):
    """One day or one week. Weekly gaps have modal_price = None and is_gap = True."""

    date: date  # the day, or the Monday that starts the week
    modal_price: float | None
    min_price: float | None
    max_price: float | None
    n_reports: int
    is_gap: bool = False
    modal_price_filled: float | None = None  # weekly only: gaps of <= 2 weeks carried forward


class PriceSeries(BaseModel):
    commodity: str
    market: str
    freq: Literal["daily", "weekly"]
    unit: str
    last_arrival_date: date | None
    stale: bool  # no price for more than 7 days
    points: list[PricePoint]
