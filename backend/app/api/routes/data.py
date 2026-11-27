"""Public read-only data routes: /meta, /prices, /analytics (rate-limited, cacheable)."""

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.time import today_ist
from app.db.session import get_session
from app.schemas.analytics import (
    RainfallImpactResponse,
    SeasonalityResponse,
    VolatilityResponse,
)
from app.schemas.meta import CommodityOut, MarketOut
from app.schemas.prices import PriceSeries
from app.services.analytics import (
    PRICE_MEASURE,
    RAINFALL_MEASURE,
    AnalyticsService,
    month_profile,
)
from app.services.catalog import (
    COMMODITY_BY_SLUG,
    MARKET_BY_SLUG,
    UNIT,
    coords,
    require_commodity,
    require_series,
)
from app.services.prices import PriceService, is_stale

router = APIRouter()

Slug = Annotated[str, Query(pattern=r"^[a-z0-9-]{1,64}$")]
CACHE_SHORT = "public, max-age=300"  # prices change daily
CACHE_LONG = "public, max-age=3600"  # config and analytics change rarely
MAX_DAILY_SPAN = timedelta(days=3 * 366)


def get_price_service(session: Annotated[Session, Depends(get_session)]) -> PriceService:
    return PriceService(session)


def get_analytics_service(session: Annotated[Session, Depends(get_session)]) -> AnalyticsService:
    return AnalyticsService(session)


# ---------- /meta (from config, no database) ----------


@router.get("/meta/commodities", response_model=list[CommodityOut], tags=["meta"])
def list_commodities(response: Response) -> list[CommodityOut]:
    response.headers["Cache-Control"] = CACHE_LONG
    return [
        CommodityOut(
            slug=c.slug,
            name=c.name,
            unit=UNIT,
            market_count=sum(c.slug in m.commodities for m in MARKET_BY_SLUG.values()),
        )
        for c in COMMODITY_BY_SLUG.values()
    ]


@router.get("/meta/markets", response_model=list[MarketOut], tags=["meta"])
def list_markets(response: Response, commodity: Slug | None = None) -> list[MarketOut]:
    if commodity is not None:
        require_commodity(commodity)
    response.headers["Cache-Control"] = CACHE_LONG
    return [
        MarketOut(
            slug=m.slug,
            name=m.market_name,
            state=m.state,
            district=m.districts[0],
            lat=coords(m)[0],
            lon=coords(m)[1],
            commodities=list(m.commodities),
        )
        for m in MARKET_BY_SLUG.values()
        if commodity is None or commodity in m.commodities
    ]


# ---------- /prices ----------


@router.get("/prices", response_model=PriceSeries, tags=["prices"])
def get_prices(
    response: Response,
    service: Annotated[PriceService, Depends(get_price_service)],
    commodity: Slug,
    market: Slug,
    freq: Literal["daily", "weekly"] = "weekly",
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
) -> PriceSeries:
    """Daily or weekly modal price history (₹/quintal) for one market x commodity."""
    require_series(commodity, market)
    today = today_ist()
    end = end or today
    default_span = timedelta(days=365) if freq == "daily" else timedelta(days=10 * 366)
    start = start or end - default_span
    if start > end:
        raise HTTPException(status_code=400, detail="'from' must be on or before 'to'.")
    if freq == "daily" and end - start > MAX_DAILY_SPAN:
        raise HTTPException(status_code=400, detail="Daily data is limited to 3 years per call.")

    last = service.last_arrival_date(commodity, market)
    response.headers["Cache-Control"] = CACHE_SHORT
    return PriceSeries(
        commodity=commodity,
        market=market,
        freq=freq,
        unit=UNIT,
        last_arrival_date=last,
        stale=is_stale(last, today),
        points=service.series(commodity, market, freq, start, end),
    )


# ---------- /analytics ----------


@router.get("/analytics/volatility", response_model=VolatilityResponse, tags=["analytics"])
def get_volatility(
    response: Response,
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    commodity: Slug,
) -> VolatilityResponse:
    """Per-market price volatility for one commodity, most volatile first."""
    require_commodity(commodity)
    response.headers["Cache-Control"] = CACHE_LONG
    return VolatilityResponse(commodity=commodity, unit=UNIT, markets=service.volatility(commodity))


@router.get("/analytics/seasonality", response_model=SeasonalityResponse, tags=["analytics"])
def get_seasonality(
    response: Response,
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    commodity: Slug,
    market: Slug,
) -> SeasonalityResponse:
    """Month x year average price, plus the typical seasonal shape across years."""
    require_series(commodity, market)
    cells = service.seasonality(commodity, market)
    response.headers["Cache-Control"] = CACHE_LONG
    return SeasonalityResponse(
        commodity=commodity, market=market, unit=UNIT, cells=cells, profile=month_profile(cells)
    )


@router.get("/analytics/rainfall-impact", response_model=RainfallImpactResponse, tags=["analytics"])
def get_rainfall_impact(
    response: Response,
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    commodity: Slug,
    market: Slug,
) -> RainfallImpactResponse:
    """Correlation between local rainfall deviation and later price changes, by lag."""
    require_series(commodity, market)
    response.headers["Cache-Control"] = CACHE_LONG
    return RainfallImpactResponse(
        commodity=commodity,
        market=market,
        rainfall_measure=RAINFALL_MEASURE,
        price_measure=PRICE_MEASURE,
        lags=service.rainfall_impact(commodity, market),
    )
