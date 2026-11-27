"""Loader row handling (pure) plus end-to-end runs against Postgres (db-marked)."""

from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.markets import COMMODITIES, MARKETS
from app.db.models import IngestionRun, QuarantineRow, RawPrice
from app.services.status import get_ingestion_status
from ingestion.datagov_client import DataGovError
from ingestion.loader import RowCollector, run_ingestion

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

SINCE = date(2025, 11, 1)


class FakeSource:
    """Serves records matching the query filters; can fail on the Nth query."""

    def __init__(self, records: list[dict[str, Any]], fail_on_query: int | None = None) -> None:
        self.records = records
        self.fail_on_query = fail_on_query
        self.queries = 0

    def iter_records(
        self, filters: dict[str, str], *, since: date, page_size: int
    ) -> Iterator[dict[str, Any]]:
        self.queries += 1
        if self.queries == self.fail_on_query:
            raise DataGovError("data.gov.in failed after 4 attempts: HTTP 502")
        for r in self.records:
            if all(r.get(k) == v for k, v in filters.items()):
                yield r


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

    first = run_ingestion(engine, source, since=SINCE, job="backfill")
    assert (first.inserted, first.duplicates, first.quarantined) == (2, 1, 1)

    second = run_ingestion(engine, source, since=SINCE, job="ingest_daily")
    assert second.inserted == 0

    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(RawPrice)) == 2
        reasons = conn.scalars(select(QuarantineRow.reason)).all()
        assert len(reasons) == 1 and reasons[0]  # seen twice, stored once, with a reason
        statuses = conn.scalars(select(IngestionRun.status)).all()
        assert statuses == ["success", "success"]
    engine.dispose()


@pytest.mark.db
def test_failed_run_is_marked_failed_and_keeps_data_consistent(migrated_db: str) -> None:
    engine = create_engine(migrated_db)
    records = [
        row(),  # first query: Onion / Maharashtra / Nashik
        row(State="Madhya Pradesh", District="Mandsaur", Market="Mandsaur"),  # second query
    ]

    with pytest.raises(DataGovError):
        run_ingestion(engine, FakeSource(records, fail_on_query=2), since=SINCE, job="ingest_daily")

    with engine.connect() as conn:
        run = conn.execute(select(IngestionRun.status, IngestionRun.error)).one()
        assert run.status == "failed" and run.error and "HTTP 502" in run.error
        # The query finished before the failure is committed whole; nothing after it is.
        assert conn.scalar(select(func.count()).select_from(RawPrice)) == 1

    # The next run fills the gap without duplicating what the failed run wrote.
    retry = run_ingestion(engine, FakeSource(records), since=SINCE, job="ingest_daily")
    assert (retry.inserted, retry.duplicates) == (1, 0)
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(RawPrice)) == 2
    engine.dispose()


@pytest.mark.db
def test_status_reports_runs_and_freshness(migrated_db: str) -> None:
    engine = create_engine(migrated_db)
    run_ingestion(engine, FakeSource([row()]), since=SINCE, job="ingest_daily")

    with Session(engine) as session:
        status = get_ingestion_status(session, today=date(2025, 11, 13))

    assert [r.status for r in status.runs] == ["success"]
    assert status.last_success_at is not None
    by_key = {(s.commodity, s.market): s for s in status.series}
    lasalgaon = by_key[("onion", "lasalgaon")]
    assert (lasalgaon.last_arrival_date, lasalgaon.days_since) == (date(2025, 11, 3), 10)
    assert lasalgaon.stale  # 10 days > 7
    assert by_key[("tomato", "kolar")].last_arrival_date is None
    assert len(status.series) == sum(len(m.commodities) for m in MARKETS)
    engine.dispose()
