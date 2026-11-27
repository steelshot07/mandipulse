"""Outlier rule, weekly aggregation/gap filling and rainfall views (needs Postgres; CI only)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Engine, create_engine, insert, text

from app.db.models import RawPrice
from ingestion.analytics import refresh_price_views
from ingestion.imd_rainfall import write_daily, write_normals
from ingestion.loader import sync_reference_data

pytestmark = pytest.mark.db


def _engine(url: str) -> tuple[Engine, int, int]:
    engine = create_engine(url)
    with engine.begin() as conn:
        markets, commodities = sync_reference_data(conn)
    return engine, markets["lasalgaon"], commodities["onion"]


def _price(mid: int, cid: int, day: date, modal: int, lo: int = 100, hi: int = 100_000) -> dict:
    return {
        "source": "test",
        "market_id": mid,
        "commodity_id": cid,
        "variety": "Red",
        "grade": "FAQ",
        "arrival_date": day,
        "min_price": Decimal(lo),
        "max_price": Decimal(hi),
        "modal_price": Decimal(modal),
        "source_market_name": "Lasalgaon",
    }


def test_outlier_rule(migrated_db: str) -> None:
    engine, mid, cid = _engine(migrated_db)
    start = date(2025, 1, 1)
    rows = [_price(mid, cid, start + timedelta(days=i), 1000) for i in range(10)]
    rows += [
        _price(mid, cid, date(2025, 1, 11), 5200),  # > 5x trailing median -> outlier
        _price(mid, cid, date(2025, 1, 12), 4900),  # < 5x -> kept
        _price(mid, cid, date(2025, 1, 13), 150),  # < 1/5 -> outlier
        _price(mid, cid, date(2025, 1, 14), 900, lo=1000, hi=2000),  # modal below min
        _price(mid, cid, date(2025, 1, 2) - timedelta(days=60), 9000),  # too little history
    ]
    with engine.begin() as conn:
        conn.execute(insert(RawPrice), rows)
        refresh_price_views(conn)
        flags = dict(
            conn.execute(
                text("SELECT arrival_date, outlier_reason FROM v_prices_clean WHERE is_outlier")
            ).all()
        )
    assert flags == {
        date(2025, 1, 11): "over_5x_from_28d_median",
        date(2025, 1, 13): "over_5x_from_28d_median",
        date(2025, 1, 14): "modal_outside_min_max",
    }
    engine.dispose()


def test_weekly_median_gaps_and_two_week_fill(migrated_db: str) -> None:
    engine, mid, cid = _engine(migrated_db)
    mon = date(2025, 1, 6)  # a Monday
    rows = [
        _price(mid, cid, mon, 1000),
        _price(mid, cid, mon + timedelta(days=1), 1200),
        _price(mid, cid, mon + timedelta(days=2), 1100),
        # weeks 2 and 3 empty -> filled; weeks 5-7 empty -> week 7 not filled
        _price(mid, cid, mon + timedelta(weeks=3), 2000),
        _price(mid, cid, mon + timedelta(weeks=7), 3000),
    ]
    with engine.begin() as conn:
        conn.execute(insert(RawPrice), rows)
        refresh_price_views(conn)
        weeks = conn.execute(
            text(
                "SELECT week_start, modal_price, is_gap, modal_price_filled, n_reports "
                "FROM v_prices_weekly ORDER BY week_start"
            )
        ).all()
    assert len(weeks) == 8  # every week from first to last report
    assert weeks[0][1:] == (1100, False, 1100, 3)  # median of 1000/1200/1100
    assert [w[2] for w in weeks] == [False, True, True, False, True, True, True, False]
    assert [w[3] for w in weeks] == [1100, 1100, 1100, 2000, 2000, 2000, None, 3000]
    engine.dispose()


def test_rainfall_final_beats_realtime_and_weekly_deviation(migrated_db: str) -> None:
    engine, mid, _ = _engine(migrated_db)
    mon = date(2025, 7, 7)
    week = [mon + timedelta(days=i) for i in range(7)]
    with engine.begin() as conn:
        write_normals(conn, mid, {d.month * 100 + d.day: 2.0 for d in week})
        write_daily(conn, [(mid, d, 5.0, "imd_final") for d in week])
        # A later real-time value must not overwrite final data...
        write_daily(conn, [(mid, week[0], 99.0, "imd_realtime")])
        row = conn.execute(
            text("SELECT rain_mm, normal_mm, deviation_mm, n_days FROM v_rainfall_weekly")
        ).one()
    assert tuple(float(x) for x in row) == (35.0, 14.0, 21.0, 7.0)
    with engine.begin() as conn:
        # ...but final data does replace real-time data.
        write_daily(conn, [(mid, date(2026, 1, 1), 1.0, "imd_realtime")])
        write_daily(conn, [(mid, date(2026, 1, 1), 4.0, "imd_final")])
        assert conn.execute(
            text("SELECT rain_mm, source FROM rainfall_daily WHERE date = '2026-01-01'")
        ).one() == (Decimal("4.00"), "imd_final")
    engine.dispose()
