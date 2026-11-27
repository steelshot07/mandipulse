"""Response models for /analytics."""

from datetime import date

from pydantic import BaseModel


class MarketVolatility(BaseModel):
    market: str
    market_name: str
    cv_52w: float | None  # std / mean of weekly prices over the last 52 weeks
    cv_all: float | None  # same over the whole history (includes long-run price trend)
    mean_abs_weekly_change_52w: float | None  # average |week-on-week % change|, as a fraction
    rolling_std_4w: float | None  # latest 4-week std of the weekly price (₹/quintal)
    last_week: date | None


class VolatilityResponse(BaseModel):
    commodity: str
    unit: str
    markets: list[MarketVolatility]


class SeasonalityCell(BaseModel):
    year: int
    month: int
    avg_price: float
    index_vs_year_avg: float | None  # 1.2 = 20% above that year's average
    n_weeks: int


class MonthProfile(BaseModel):
    month: int
    avg_index: float  # average of index_vs_year_avg across complete years
    n_years: int


class SeasonalityResponse(BaseModel):
    commodity: str
    market: str
    unit: str
    cells: list[SeasonalityCell]
    profile: list[MonthProfile]


class LagCorrelation(BaseModel):
    lag_weeks: int
    correlation: float | None
    n: int
    significant: bool  # |r| > 1.96 / sqrt(n), i.e. roughly p < 0.05


class RainfallImpactResponse(BaseModel):
    commodity: str
    market: str
    rainfall_measure: str
    price_measure: str
    lags: list[LagCorrelation]
