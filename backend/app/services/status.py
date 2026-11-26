"""Ingestion status: recent runs and per-series data freshness."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.markets import MARKETS
from app.db.models import Commodity, IngestionRun, Market, RawPrice
from app.schemas.status import IngestionRunOut, IngestionStatusResponse, SeriesFreshness

RECENT_RUNS = 14
# Rules.md §5: a series with no price for more than 7 days counts as stale.
STALE_AFTER_DAYS = 7


def get_ingestion_status(session: Session, today: date) -> IngestionStatusResponse:
    runs = session.scalars(
        select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(RECENT_RUNS)
    ).all()
    last_success_at = session.scalar(
        select(func.max(IngestionRun.finished_at)).where(IngestionRun.status == "success")
    )
    latest = {
        (market, commodity): last
        for market, commodity, last in session.execute(
            select(Market.slug, Commodity.slug, func.max(RawPrice.arrival_date))
            .join(Market, Market.id == RawPrice.market_id)
            .join(Commodity, Commodity.id == RawPrice.commodity_id)
            .group_by(Market.slug, Commodity.slug)
        )
    }

    series = []
    for market in MARKETS:  # every configured series, even one with no rows yet
        for commodity in market.commodities:
            last = latest.get((market.slug, commodity))
            days = (today - last).days if last else None
            series.append(
                SeriesFreshness(
                    commodity=commodity,
                    market=market.slug,
                    market_name=market.market_name,
                    last_arrival_date=last,
                    days_since=days,
                    stale=days is None or days > STALE_AFTER_DAYS,
                )
            )
    series.sort(key=lambda s: (s.commodity, s.market))

    return IngestionStatusResponse(
        last_success_at=last_success_at,
        stale_after_days=STALE_AFTER_DAYS,
        runs=[IngestionRunOut.model_validate(r, from_attributes=True) for r in runs],
        series=series,
    )
