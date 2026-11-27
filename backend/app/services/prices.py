"""Price history queries (daily from v_prices_clean, weekly from v_prices_weekly)."""

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.prices import PricePoint
from app.services.status import STALE_AFTER_DAYS

_SERIES = """
    JOIN markets m ON m.id = v.market_id AND m.slug = :market
    JOIN commodities c ON c.id = v.commodity_id AND c.slug = :commodity
"""

_WEEKLY = f"""
SELECT v.week_start, v.modal_price, v.min_price, v.max_price, v.n_reports, v.is_gap,
       v.modal_price_filled
  FROM v_prices_weekly v {_SERIES}
 WHERE v.week_start BETWEEN :start AND :end
 ORDER BY v.week_start
"""

# Daily: median of that day's non-outlier reports across varieties (same rule as weekly).
_DAILY = f"""
SELECT v.arrival_date,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY v.modal_price),
       min(v.min_price), max(v.max_price), count(*)
  FROM v_prices_clean v {_SERIES}
 WHERE NOT v.is_outlier AND v.arrival_date BETWEEN :start AND :end
 GROUP BY v.arrival_date
 ORDER BY v.arrival_date
"""

_LAST = f"SELECT max(v.arrival_date) FROM raw_prices v {_SERIES}"


def _f(value: object) -> float | None:
    return None if value is None else float(value)  # type: ignore[arg-type]


def is_stale(last: date | None, today: date) -> bool:
    return last is None or (today - last).days > STALE_AFTER_DAYS


class PriceService:
    def __init__(self, session: Session | None) -> None:
        self._session = session

    def _db(self) -> Session:
        if self._session is None:
            raise RuntimeError("PriceService has no database session")
        return self._session

    def last_arrival_date(self, commodity: str, market: str) -> date | None:
        params = {"commodity": commodity, "market": market}
        last: date | None = self._db().execute(text(_LAST), params).scalar()
        return last

    def series(
        self, commodity: str, market: str, freq: str, start: date, end: date
    ) -> list[PricePoint]:
        params = {"commodity": commodity, "market": market, "start": start, "end": end}
        if freq == "weekly":
            return [
                PricePoint(
                    date=r[0],
                    modal_price=_f(r[1]),
                    min_price=_f(r[2]),
                    max_price=_f(r[3]),
                    n_reports=r[4],
                    is_gap=r[5],
                    modal_price_filled=_f(r[6]),
                )
                for r in self._db().execute(text(_WEEKLY), params)
            ]
        return [
            PricePoint(
                date=r[0],
                modal_price=_f(r[1]),
                min_price=_f(r[2]),
                max_price=_f(r[3]),
                n_reports=r[4],
            )
            for r in self._db().execute(text(_DAILY), params)
        ]
