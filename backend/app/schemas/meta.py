"""Response models for /meta."""

from pydantic import BaseModel


class CommodityOut(BaseModel):
    slug: str
    name: str
    unit: str
    market_count: int


class MarketOut(BaseModel):
    slug: str
    name: str
    state: str
    district: str
    lat: float
    lon: float
    commodities: list[str]
