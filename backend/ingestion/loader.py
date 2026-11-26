"""Load data.gov.in mandi prices into raw_prices (shared by backfill and the daily job).

* Markets and commodities are synced from app.core.markets first.
* One API query per (commodity, state, district); rows are kept only if their
  (state, market name) matches a configured alias for a market that tracks that commodity.
* Every in-scope row is validated; failures go to quarantine_rows with a reason.
* Every distinct report is kept: since 2024 the source sometimes has 2+ reports with
  different prices for the same market/variety/grade/day (separate lots or revisions);
  the weekly cleaning view takes the median. Identical reports (e.g. the same row under
  an old and a new market name) are stored once and counted as duplicates.
* Inserts are idempotent (ON CONFLICT DO NOTHING on the full key): a re-run inserts 0.
* Every run is logged in ingestion_runs; the CLIs exit non-zero on failure.
"""

import json
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol

from pydantic import ValidationError
from sqlalchemy import Connection, Engine, select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.markets import (
    COMMODITIES,
    MARKETS,
    CommodityConfig,
    MarketConfig,
    alias_index,
    fetch_plan,
    normalise,
)
from app.db.models import Commodity, IngestionRun, Market, RawPrice
from app.db.session import get_engine
from ingestion.datagov_client import DataGovClient, Record, parse_source_date
from ingestion.records import DataGovPriceRecord

logger = get_logger(__name__)

SOURCE = "datagov"
BATCH_SIZE = 2_000


class RecordSource(Protocol):
    """Anything that yields raw API records (DataGovClient, or a fake in tests)."""

    def iter_records(
        self, filters: dict[str, str], *, since: date, page_size: int
    ) -> Iterator[Record]: ...


# market_id, commodity_id, variety, grade, date, min, max, modal (= uq_raw_prices_key)
PriceKey = tuple[int, int, str, str, date, Decimal, Decimal, Decimal]


@dataclass
class Stats:
    fetched: int = 0
    in_scope: int = 0
    duplicates: int = 0
    inserted: int = 0
    quarantined: int = 0
    unmapped: Counter[str] = field(default_factory=Counter)


class RowCollector:
    """Turns raw API records into validated raw_prices rows and quarantine rows (no I/O)."""

    def __init__(
        self,
        market_ids: dict[str, int],
        commodity_ids: dict[str, int],
        since: date,
    ) -> None:
        self._index = alias_index()
        self._market_ids = market_ids
        self._commodity_ids = commodity_ids
        self._since = since
        self._seen: set[PriceKey] = set()
        self.stats = Stats()
        self.rows: list[dict[str, Any]] = []
        self.quarantine: list[dict[str, Any]] = []

    def add(self, raw: Record, commodity: CommodityConfig) -> None:
        self.stats.fetched += 1
        market = self._match(raw, commodity)
        if market is None:
            return
        arrival = parse_source_date(raw.get("Arrival_Date"))
        if arrival is not None and arrival < self._since:
            return  # the last page overshoots the window; not our data, so not an error
        try:
            rec = DataGovPriceRecord.model_validate(raw)
        except ValidationError as exc:
            self._quarantine(raw, "invalid: " + _describe(exc))
            return
        self.stats.in_scope += 1

        market_id = self._market_ids[market.slug]
        commodity_id = self._commodity_ids[commodity.slug]
        key: PriceKey = (
            market_id,
            commodity_id,
            rec.variety,
            rec.grade,
            rec.arrival_date,
            rec.min_price,
            rec.max_price,
            rec.modal_price,
        )
        if key in self._seen:
            self.stats.duplicates += 1
            return
        self._seen.add(key)
        self.rows.append(
            {
                "source": SOURCE,
                "market_id": market_id,
                "commodity_id": commodity_id,
                "variety": rec.variety,
                "grade": rec.grade,
                "arrival_date": rec.arrival_date,
                "min_price": rec.min_price,
                "max_price": rec.max_price,
                "modal_price": rec.modal_price,
                "source_market_name": rec.market,
            }
        )

    def _match(self, raw: Record, commodity: CommodityConfig) -> MarketConfig | None:
        if normalise(str(raw.get("Commodity", ""))) != normalise(commodity.name):
            return None
        state, name = str(raw.get("State", "")), str(raw.get("Market", ""))
        market = self._index.get((normalise(state), normalise(name)))
        if market is None or commodity.slug not in market.commodities:
            self.stats.unmapped[f"{state.strip()} / {name.strip()}"] += 1
            return None
        return market

    def _quarantine(self, raw: Record, reason: str) -> None:
        self.stats.quarantined += 1
        self.quarantine.append({"source": SOURCE, "payload": raw, "reason": reason})


def _describe(exc: ValidationError) -> str:
    """Name the failing fields and error types (no values, they're in the payload)."""
    parts = [f"{'.'.join(str(p) for p in e['loc'])} ({e['type']})" for e in exc.errors()]
    return ", ".join(parts)


def sync_reference_data(conn: Connection) -> tuple[dict[str, int], dict[str, int]]:
    """Upsert markets and commodities from config; return slug -> id maps."""
    for c in COMMODITIES:
        stmt = insert(Commodity).values(slug=c.slug, name=c.name)
        conn.execute(stmt.on_conflict_do_update(index_elements=["slug"], set_={"name": c.name}))
    for m in MARKETS:
        values = {
            "slug": m.slug,
            "market_name": m.market_name,
            "state": m.state,
            "district": m.districts[0],
        }
        stmt = insert(Market).values(**values)
        conn.execute(stmt.on_conflict_do_update(index_elements=["slug"], set_=values))
    markets = {slug: id_ for slug, id_ in conn.execute(select(Market.slug, Market.id))}
    commodities = {slug: id_ for slug, id_ in conn.execute(select(Commodity.slug, Commodity.id))}
    return markets, commodities


def write_rows(conn: Connection, rows: list[dict[str, Any]]) -> int:
    """Insert price rows in batches, skipping ones already stored. Return rows inserted."""
    inserted = 0
    for start in range(0, len(rows), BATCH_SIZE):
        stmt = (
            insert(RawPrice)
            .values(rows[start : start + BATCH_SIZE])
            .on_conflict_do_nothing(constraint="uq_raw_prices_key")
            .returning(RawPrice.id)
        )
        inserted += len(conn.execute(stmt).all())
    return inserted


_INSERT_QUARANTINE_IF_NEW = text("""
    INSERT INTO quarantine_rows (ingestion_run_id, source, payload, reason)
    SELECT CAST(:run_id AS integer), CAST(:source AS varchar), CAST(:payload AS jsonb),
           CAST(:reason AS text)
    WHERE NOT EXISTS (
        SELECT 1 FROM quarantine_rows
        WHERE source = CAST(:source AS varchar)
          AND reason = CAST(:reason AS text)
          AND payload = CAST(:payload AS jsonb)
    )
    """)


def write_quarantine(conn: Connection, rows: list[dict[str, Any]], run_id: int) -> None:
    """Store rejected rows, skipping ones already quarantined by an earlier run.

    The daily job re-reads 10 days, so the same bad source row is seen ~10 times.
    """
    if rows:
        params = [
            {
                "run_id": run_id,
                "source": r["source"],
                "payload": json.dumps(r["payload"]),
                "reason": r["reason"],
            }
            for r in rows
        ]
        conn.execute(_INSERT_QUARANTINE_IF_NEW, params)


def run_ingestion(
    engine: Engine,
    client: RecordSource,
    *,
    since: date,
    job: str,
    page_size: int = 10_000,
) -> Stats:
    """Load every v1 series from ``since`` onwards and record the run in ingestion_runs.

    On any error the run is marked failed (with the error kept server-side) and the
    exception is re-raised. Queries already written stay committed: they are complete,
    valid rows, and a re-run skips them.
    """
    with engine.begin() as conn:
        run_id = conn.execute(
            insert(IngestionRun).values(job=job, status="running").returning(IngestionRun.id)
        ).scalar_one()
        market_ids, commodity_ids = sync_reference_data(conn)

    collector = RowCollector(market_ids, commodity_ids, since)
    try:
        for commodity, state, district in fetch_plan():
            filters = {"Commodity": commodity.name, "State": state, "District": district}
            before = collector.stats.fetched
            for raw in client.iter_records(filters, since=since, page_size=page_size):
                collector.add(raw, commodity)
            rows, quarantine = collector.rows, collector.quarantine
            collector.rows, collector.quarantine = [], []
            # Commit per query so a later failure keeps earlier progress (re-runs are safe).
            with engine.begin() as conn:
                inserted = write_rows(conn, rows)
                write_quarantine(conn, quarantine, run_id)
            collector.stats.inserted += inserted
            logger.info(
                "%s / %s / %s: fetched %d, kept %d, inserted %d, quarantined %d",
                commodity.name,
                state,
                district,
                collector.stats.fetched - before,
                len(rows),
                inserted,
                len(quarantine),
            )
    except Exception as exc:
        _finish(engine, run_id, collector.stats, "failed", f"{type(exc).__name__}: {exc}"[:2000])
        raise

    _finish(engine, run_id, collector.stats, "success", None)
    return collector.stats


def _finish(engine: Engine, run_id: int, stats: Stats, status: str, error: str | None) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(IngestionRun)
            .where(IngestionRun.id == run_id)
            .values(
                status=status,
                finished_at=datetime.now().astimezone(),
                rows_fetched=stats.fetched,
                rows_inserted=stats.inserted,
                rows_quarantined=stats.quarantined,
                error=error,
            )
        )


def _log_summary(job: str, stats: Stats) -> None:
    logger.info(
        "%s done: fetched %d, in scope %d, inserted %d, duplicates %d, quarantined %d",
        job,
        stats.fetched,
        stats.in_scope,
        stats.inserted,
        stats.duplicates,
        stats.quarantined,
    )
    _log_possible_renames(stats.unmapped.items())


def _log_possible_renames(unmapped: Iterable[tuple[str, int]]) -> None:
    """Warn about unmapped names that look like a configured market (likely a new rename)."""
    stems = {
        normalise(alias).replace("apmc", "").strip(" ()") for m in MARKETS for alias in m.aliases
    }
    for name, count in sorted(unmapped):
        market_part = normalise(name.split(" / ", 1)[-1])
        if any(stem and stem in market_part for stem in stems):
            logger.warning("Unmapped market name resembles a v1 market: %r (%d rows)", name, count)


def run_cli(job: str, since: date, page_size: int) -> int:
    """Shared CLI body: configure logging, run, return a process exit code."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("%s: loading arrivals since %s", job, since)
    try:
        with DataGovClient(settings.datagov_api_key) as client:
            stats = run_ingestion(get_engine(), client, since=since, job=job, page_size=page_size)
    except Exception:
        logger.exception("%s failed", job)
        return 1
    _log_summary(job, stats)
    return 0
