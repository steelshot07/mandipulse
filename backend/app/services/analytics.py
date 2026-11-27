"""Volatility, seasonality and rainfall-impact queries over the analytics views."""

import math

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.analytics import (
    LagCorrelation,
    MarketVolatility,
    MonthProfile,
    SeasonalityCell,
)

MAX_LAG_WEEKS = 12
RAINFALL_MEASURE = (
    "Rainfall over the 4 weeks to week t minus the 1991-2020 normal (mm), "
    "averaged over ~55 km around the mandi"
)
PRICE_MEASURE = "Change in weekly modal price over the 4 weeks ending at week t + lag_weeks"

_VOLATILITY = """
WITH w AS (
    SELECT v.market_id, v.week_start, v.modal_price, v.rolling_std_4w, v.pct_change_1w
      FROM v_volatility v JOIN commodities c ON c.id = v.commodity_id AND c.slug = :commodity
), last AS (
    SELECT market_id, max(week_start) AS last_week FROM w WHERE modal_price IS NOT NULL
     GROUP BY market_id
)
SELECT m.slug, m.market_name,
       stddev_samp(w.modal_price) FILTER (WHERE w.week_start > l.last_week - 364)
         / NULLIF(avg(w.modal_price) FILTER (WHERE w.week_start > l.last_week - 364), 0),
       stddev_samp(w.modal_price) / NULLIF(avg(w.modal_price), 0),
       avg(abs(w.pct_change_1w)) FILTER (WHERE w.week_start > l.last_week - 364),
       (array_agg(w.rolling_std_4w ORDER BY w.week_start DESC)
          FILTER (WHERE w.rolling_std_4w IS NOT NULL))[1],
       l.last_week
  FROM w JOIN last l USING (market_id) JOIN markets m ON m.id = w.market_id
 GROUP BY m.slug, m.market_name, l.last_week
 ORDER BY 3 DESC NULLS LAST
"""

_SEASONALITY = """
SELECT s.year, s.month, s.avg_price, s.index_vs_year_avg, s.n_weeks
  FROM v_seasonality s
  JOIN markets m ON m.id = s.market_id AND m.slug = :market
  JOIN commodities c ON c.id = s.commodity_id AND c.slug = :commodity
 ORDER BY s.year, s.month
"""

# corr(rain deviation summed over weeks t-3..t, 4-week price change ending at t + lag).
# Only complete weeks of rain (7 days) and complete 4-week windows are used.
_RAIN_IMPACT = """
WITH rain AS (
    SELECT r.week_start,
           sum(r.deviation_mm) OVER w4 AS dev_4w,
           count(*) OVER w4 AS n_4w,
           r.week_start - lag(r.week_start, 3) OVER (ORDER BY r.week_start) AS span
      FROM v_rainfall_weekly r JOIN markets m ON m.id = r.market_id AND m.slug = :market
     WHERE r.n_days = 7
    WINDOW w4 AS (ORDER BY r.week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
), price AS (
    SELECT v.week_start, v.pct_change_4w
      FROM v_volatility v
      JOIN markets m ON m.id = v.market_id AND m.slug = :market
      JOIN commodities c ON c.id = v.commodity_id AND c.slug = :commodity
     WHERE v.pct_change_4w IS NOT NULL
)
SELECT k.lag, corr(rain.dev_4w, price.pct_change_4w), count(price.pct_change_4w)
  FROM generate_series(0, :max_lag) AS k(lag)
  JOIN rain ON rain.n_4w = 4 AND rain.span = 21
  JOIN price ON price.week_start = rain.week_start + k.lag * 7
 GROUP BY k.lag ORDER BY k.lag
"""


def _f(value: object) -> float | None:
    return None if value is None else float(value)  # type: ignore[arg-type]


def month_profile(cells: list[SeasonalityCell]) -> list[MonthProfile]:
    """Average seasonal index per calendar month, using only years with all 12 months."""
    months_per_year: dict[int, int] = {}
    for cell in cells:
        months_per_year[cell.year] = months_per_year.get(cell.year, 0) + 1
    full_years = {y for y, n in months_per_year.items() if n == 12}
    profile = []
    for month in range(1, 13):
        values = [
            c.index_vs_year_avg
            for c in cells
            if c.month == month and c.year in full_years and c.index_vs_year_avg is not None
        ]
        if values:
            profile.append(
                MonthProfile(month=month, avg_index=sum(values) / len(values), n_years=len(values))
            )
    return profile


def lag_correlation(lag: int, r: float | None, n: int) -> LagCorrelation:
    """Flag |r| above the ~95% threshold for no correlation (1.96 / sqrt(n))."""
    significant = r is not None and n > 3 and abs(r) > 1.96 / math.sqrt(n)
    return LagCorrelation(lag_weeks=lag, correlation=r, n=n, significant=significant)


class AnalyticsService:
    def __init__(self, session: Session | None) -> None:
        self._session = session

    def _db(self) -> Session:
        if self._session is None:
            raise RuntimeError("AnalyticsService has no database session")
        return self._session

    def volatility(self, commodity: str) -> list[MarketVolatility]:
        return [
            MarketVolatility(
                market=r[0],
                market_name=r[1],
                cv_52w=_f(r[2]),
                cv_all=_f(r[3]),
                mean_abs_weekly_change_52w=_f(r[4]),
                rolling_std_4w=_f(r[5]),
                last_week=r[6],
            )
            for r in self._db().execute(text(_VOLATILITY), {"commodity": commodity})
        ]

    def seasonality(self, commodity: str, market: str) -> list[SeasonalityCell]:
        params = {"commodity": commodity, "market": market}
        return [
            SeasonalityCell(
                year=r[0],
                month=r[1],
                avg_price=float(r[2]),
                index_vs_year_avg=_f(r[3]),
                n_weeks=r[4],
            )
            for r in self._db().execute(text(_SEASONALITY), params)
        ]

    def rainfall_impact(self, commodity: str, market: str) -> list[LagCorrelation]:
        params = {"commodity": commodity, "market": market, "max_lag": MAX_LAG_WEEKS}
        return [
            lag_correlation(r[0], _f(r[1]), r[2])
            for r in self._db().execute(text(_RAIN_IMPACT), params)
        ]
