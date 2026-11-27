"""Lookups of v1 commodities and markets from config, with 404s for unknown names."""

from fastapi import HTTPException

from app.core.markets import COMMODITIES, MARKET_COORDS, MARKETS, CommodityConfig, MarketConfig

COMMODITY_BY_SLUG = {c.slug: c for c in COMMODITIES}
MARKET_BY_SLUG = {m.slug: m for m in MARKETS}
UNIT = "₹/quintal"


def require_commodity(slug: str) -> CommodityConfig:
    commodity = COMMODITY_BY_SLUG.get(slug)
    if commodity is None:  # never echo the input back (Rules.md §6)
        raise HTTPException(status_code=404, detail="Unknown commodity.")
    return commodity


def require_series(commodity_slug: str, market_slug: str) -> tuple[CommodityConfig, MarketConfig]:
    commodity = require_commodity(commodity_slug)
    market = MARKET_BY_SLUG.get(market_slug)
    if market is None:
        raise HTTPException(status_code=404, detail="Unknown market.")
    if commodity.slug not in market.commodities:
        raise HTTPException(status_code=404, detail="This market isn't tracked for that commodity.")
    return commodity, market


def coords(market: MarketConfig) -> tuple[float, float]:
    return MARKET_COORDS[market.slug]
