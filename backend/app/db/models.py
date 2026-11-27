"""SQLAlchemy ORM models (see docs/Architecture.md §3)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

PRICE = Numeric(12, 2)


class Base(DeclarativeBase):
    """Declarative base shared by all models and used by Alembic autogenerate."""


class Market(Base):
    """A v1 mandi. Rows are synced from app.core.markets, never edited by hand."""

    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    market_name: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(64))
    district: Mapped[str] = mapped_column(String(64))
    lat: Mapped[float | None]
    lon: Mapped[float | None]
    census_district: Mapped[str | None] = mapped_column(String(64))


class Commodity(Base):
    """A v1 commodity. Prices are always stored in ₹/quintal."""

    __tablename__ = "commodities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    unit: Mapped[str] = mapped_column(String(16), server_default="₹/quintal")


class RawPrice(Base):
    """Insert-only daily price reports exactly as published (cleaning happens in views)."""

    __tablename__ = "raw_prices"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "market_id",
            "commodity_id",
            "variety",
            "grade",
            "arrival_date",
            "min_price",
            "max_price",
            "modal_price",
            name="uq_raw_prices_key",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    commodity_id: Mapped[int] = mapped_column(ForeignKey("commodities.id"), index=True)
    variety: Mapped[str] = mapped_column(String(64))
    grade: Mapped[str] = mapped_column(String(32))
    arrival_date: Mapped[date] = mapped_column(Date, index=True)
    min_price: Mapped[Decimal] = mapped_column(PRICE)
    max_price: Mapped[Decimal] = mapped_column(PRICE)
    modal_price: Mapped[Decimal] = mapped_column(PRICE)
    arrivals_tonnes: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    source_market_name: Mapped[str] = mapped_column(String(128))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IngestionRun(Base):
    """One execution of an ingestion job, for the status page and failure alerts."""

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))  # running | success | failed
    rows_fetched: Mapped[int] = mapped_column(Integer, server_default="0")
    rows_inserted: Mapped[int] = mapped_column(Integer, server_default="0")
    rows_quarantined: Mapped[int] = mapped_column(Integer, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)


class QuarantineRow(Base):
    """A rejected source row, kept with the reason so nothing is dropped silently."""

    __tablename__ = "quarantine_rows"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ingestion_run_id: Mapped[int | None] = mapped_column(ForeignKey("ingestion_runs.id"))
    source: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RainfallDaily(Base):
    """Mean IMD gridded rainfall over a +/- 0.5 deg box around a mandi, per day."""

    __tablename__ = "rainfall_daily"

    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    rain_mm: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    source: Mapped[str] = mapped_column(String(16))  # imd_final | imd_realtime
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RainfallNormal(Base):
    """1991-2020 daily rainfall climatology for the same box, keyed by month*100 + day."""

    __tablename__ = "rainfall_normals"

    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), primary_key=True)
    month_day: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    normal_mm: Mapped[Decimal] = mapped_column(Numeric(7, 2))
