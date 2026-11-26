"""Backfill row handling (pure) and an idempotent end-to-end run (needs Postgres)."""

import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, func, select

from app.core.markets import COMMODITIES, MARKETS
from app.db.models import IngestionRun, QuarantineRow, RawPrice
from ingestion.backfill import RowCollector, run_backfill

ONION = next(c for c in COMMODITIES if c.slug == "onion")
POTATO = next(c for c in COMMODITIES if c.slug == "potato")
MARKET_IDS = {m.slug: i for i, m in enumerate(MARKETS, start=1)}
COMMODITY_IDS = {c.slug: i for i, c in enumerate(COMMODITIES, start=1)}


def row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "State": "Maharashtra",
        "District": "Nashik",
        "Market": "Lasalgaon",
        "Commodity": "Onion",
        "Variety": "Red",
        "Grade": "FAQ",
        "Arrival_Date": "03/11/2025",
        "Min_Price": "1000",
        "Max_Price": "2500",
        "Modal_Price": "2100",
    }
    base.update(overrides)
    return base


def collector(since: date = date(2019, 1, 1)) -> RowCollector:
    return RowCollector(MARKET_IDS, COMMODITY_IDS, since)


def test_old_and_new_names_map_to_one_market_and_identical_repeat_is_deduped() -> None:
    c = collector()
    c.add(row(Market="Lasalgaon"), ONION)
    c.add(row(Market="Lasalgaon APMC"), ONION)  # same day, same prices, new name
    c.add(row(Market="APMC Lasalgaon ", Arrival_Date="04/11/2025"), ONION)
    assert len(c.rows) == 2
    assert {r["market_id"] for r in c.rows} == {MARKET_IDS["lasalgaon"]}
    assert c.stats.duplicates == 1
    assert c.quarantine == []


def test_distinct_same_day_reports_are_all_kept() -> None:
    c = collector()
    c.add(row(Market="Lasalgaon"), ONION)
    c.add(row(Market="Lasalgaon", Modal_Price="2200"), ONION)  # second lot, same day
    assert sorted(r["modal_price"] for r in c.rows) == [2100, 2200]
    assert c.quarantine == [] and c.stats.duplicates == 0


def test_invalid_in_scope_row_is_quarantined() -> None:
    c = collector()
    c.add(row(Modal_Price="0"), ONION)
    assert c.rows == []
    assert "modal_price" in c.quarantine[0]["reason"].lower()
    assert c.quarantine[0]["payload"]["Modal_Price"] == "0"


def test_unmapped_market_is_counted_not_quarantined() -> None:
    c = collector()
    c.add(row(Market="Yeola"), ONION)
    assert c.rows == [] and c.quarantine == []
    assert c.stats.unmapped["Maharashtra / Yeola"] == 1


def test_market_only_kept_for_its_commodities() -> None:
    c = collector()
    c.add(row(Commodity="Potato"), POTATO)  # Lasalgaon tracks onion only
    c.add(row(State="NCT of Delhi", District="Delhi", Market="Azadpur", Commodity="Potato"), POTATO)
    assert [r["market_id"] for r in c.rows] == [MARKET_IDS["azadpur"]]


def test_rows_before_since_are_skipped_silently() -> None:
    c = collector(since=date(2025, 11, 4))
    c.add(row(Arrival_Date="03/11/2025"), ONION)
    c.add(row(Arrival_Date="01/01/2014", Min_Price="0", Max_Price="0"), ONION)  # old + invalid
    assert c.rows == [] and c.quarantine == []


# --- End-to-end against a disposable Postgres (CI service container) ---

TEST_DB = os.environ.get("TEST_DATABASE_URL")


class FakeSource:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records

    def iter_records(self, filters: dict[str, str], *, since: date) -> Iterator[dict[str, Any]]:
        for r in self.records:
            if all(r.get(k) == v for k, v in filters.items()):
                yield r


@pytest.fixture
def migrated_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    if not TEST_DB:
        pytest.skip("TEST_DATABASE_URL not set")
    from alembic.config import Config

    from alembic import command
    from app.core.config import get_settings

    monkeypatch.setenv("DATABASE_URL", TEST_DB)
    get_settings.cache_clear()
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")
    try:
        yield get_settings().sqlalchemy_url
    finally:
        command.downgrade(cfg, "base")
        get_settings.cache_clear()


@pytest.mark.db
def test_backfill_is_idempotent(migrated_db: str) -> None:
    engine = create_engine(migrated_db)
    source = FakeSource(
        [
            row(),
            row(Market="Lasalgaon APMC"),  # identical overlap -> deduped
            row(Arrival_Date="04/11/2025", Modal_Price="2300"),
            row(Arrival_Date="05/11/2025", Modal_Price="0"),  # -> quarantine
        ]
    )

    first = run_backfill(engine, source)
    assert (first.inserted, first.duplicates, first.quarantined) == (2, 1, 1)

    second = run_backfill(engine, source)
    assert second.inserted == 0

    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(RawPrice)) == 2
        reasons = conn.scalars(select(QuarantineRow.reason)).all()
        assert reasons and all(reasons)
        statuses = conn.scalars(select(IngestionRun.status)).all()
        assert statuses == ["success", "success"]
    engine.dispose()
