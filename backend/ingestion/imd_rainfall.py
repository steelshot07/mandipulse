"""IMD gridded rainfall around each mandi -> rainfall_daily (+ rainfall_normals).

Source: IMD Pune 0.25 deg daily gridded rainfall (129 lat x 135 lon, 6.5-38.5 N, 66.5-100 E,
-999 = no data). Final data comes as one netCDF file per year (published the following
year); the current year comes from the real-time feed, one raw float32 grid per day.
Unlike data.gov.in, IMD is reachable from outside India (checked 2026-11-27), so this job
runs on GitHub Actions.

For each mandi we average the grid cells within +/- 0.5 deg (about 55 km) of it. Normals
are the 1991-2020 average for each calendar day, smoothed with a 31-day window.

Usage:
  python -m ingestion.imd_rainfall backfill [--from-year 2019]   # normals + history (~1 GB)
  python -m ingestion.imd_rainfall recent [--days 21]            # weekly job (real-time feed)
"""

import argparse
import io
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import httpx
import numpy as np
import numpy.typing as npt
from scipy.io import netcdf_file
from sqlalchemy import Connection, Engine, select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.markets import MARKET_COORDS
from app.core.time import today_ist
from app.db.models import IngestionRun, Market, RainfallNormal
from app.db.session import get_engine
from ingestion.datagov_client import USER_AGENT

logger = get_logger(__name__)

YEARLY_URL = "https://www.imdpune.gov.in/cmpg/Griddata/RF25.php"
REALTIME_URL = "https://www.imdpune.gov.in/cmpg/Realtimedata/Rainfall/rain.php"
GRID_LAT = 6.5 + 0.25 * np.arange(129)
GRID_LON = 66.5 + 0.25 * np.arange(135)
MISSING = -999.0
BOX_DEG = 0.5
NORMAL_YEARS = range(1991, 2021)  # WMO standard normal period
SMOOTH_DAYS = 31

Grid = npt.NDArray[np.float64]  # (..., 129, 135)


class ImdError(RuntimeError):
    """IMD still failing after retries."""


class ImdClient:
    """Downloads IMD grids with timeouts and retries (Rules.md §5)."""

    def __init__(
        self,
        *,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep
        # Yearly files are ~25 MB, so allow a long read; connecting must still be quick.
        self._http = httpx.Client(
            timeout=httpx.Timeout(120.0, connect=30.0),
            headers={"User-Agent": USER_AGENT},
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "ImdClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _post(self, url: str, data: dict[str, str]) -> bytes:
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._http.post(url, data=data)
                if resp.status_code < 500 and resp.status_code != 429:
                    resp.raise_for_status()
                    return resp.content
                problem = f"HTTP {resp.status_code}"
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                problem = type(exc).__name__
            except httpx.HTTPStatusError as exc:
                raise ImdError(f"HTTP {exc.response.status_code} from IMD") from None
            if attempt == self._max_retries:
                raise ImdError(f"IMD failed after {attempt + 1} attempts: {problem}")
            delay = self._backoff_base * 2**attempt
            logger.warning("IMD %s, retrying in %.0fs", problem, delay)
            self._sleep(delay)
        raise AssertionError("unreachable")

    def fetch_year(self, year: int) -> tuple[list[date], Grid] | None:
        """Final grids for a whole year, or None if IMD hasn't published that year yet."""
        content = self._post(YEARLY_URL, {"RF25": str(year)})
        return parse_yearly(content) if content else None

    def fetch_day(self, day: date) -> Grid | None:
        """Real-time grid for one day, or None if it isn't available (yet)."""
        content = self._post(REALTIME_URL, {"rain": day.strftime("%d%m%Y")})
        return parse_realtime(content) if content else None


def parse_yearly(content: bytes) -> tuple[list[date], Grid]:
    """Parse an IMD yearly netCDF file into (dates, grids[day, lat, lon])."""
    with netcdf_file(io.BytesIO(content), "r", mmap=False) as nc:
        lat = np.asarray(nc.variables["LATITUDE"][:], dtype=float)
        lon = np.asarray(nc.variables["LONGITUDE"][:], dtype=float)
        if not (np.allclose(lat, GRID_LAT) and np.allclose(lon, GRID_LON)):
            raise ImdError("unexpected IMD grid layout")
        days = np.asarray(nc.variables["TIME"][:], dtype=float)
        rain = np.array(nc.variables["RAINFALL"][:], dtype=float)
    origin = date(1900, 12, 31)  # TIME units: "days since 1900-12-31"
    return [origin + timedelta(days=int(d)) for d in days], rain


def parse_realtime(content: bytes) -> Grid:
    """Parse one real-time day: raw little-endian float32, row-major (lat, lon)."""
    values = np.frombuffer(content, dtype="<f4")
    if values.size != GRID_LAT.size * GRID_LON.size:
        raise ImdError(f"unexpected real-time grid size {values.size}")
    return values.reshape(GRID_LAT.size, GRID_LON.size).astype(float)


def box_masks(coords: dict[str, tuple[float, float]]) -> dict[str, npt.NDArray[np.bool_]]:
    """Grid cells within +/- BOX_DEG of each mandi."""
    lat_grid, lon_grid = np.meshgrid(GRID_LAT, GRID_LON, indexing="ij")
    masks = {}
    for slug, (lat, lon) in coords.items():
        mask = (np.abs(lat_grid - lat) <= BOX_DEG + 1e-9) & (
            np.abs(lon_grid - lon) <= BOX_DEG + 1e-9
        )
        if not mask.any():
            raise ValueError(f"{slug} is outside the IMD grid")
        masks[slug] = mask
    return masks


def box_mean(grids: Grid, mask: npt.NDArray[np.bool_]) -> npt.NDArray[np.float64]:
    """Mean rain over the masked cells for each day, ignoring missing cells (NaN if none)."""
    cells = grids[..., mask]  # (days, n_cells) or (n_cells,)
    cells = np.where(cells <= MISSING + 1, np.nan, cells)
    valid = np.isfinite(cells).sum(axis=-1)
    total = np.nansum(cells, axis=-1)
    return np.where(valid > 0, total / np.maximum(valid, 1), np.nan)


def month_day(d: date) -> int:
    return d.month * 100 + d.day


# Calendar of a leap year, so 29 Feb gets a slot; used to order and smooth the normals.
_LEAP_DAYS = [date(2000, 1, 1) + timedelta(days=i) for i in range(366)]


@dataclass
class Climatology:
    """Running sums per (market, calendar day) for the normal period."""

    sums: dict[str, npt.NDArray[np.float64]]
    counts: dict[str, npt.NDArray[np.float64]]

    @classmethod
    def empty(cls, slugs: Iterable[str]) -> "Climatology":
        return cls({s: np.zeros(366) for s in slugs}, {s: np.zeros(366) for s in slugs})

    def add(self, slug: str, days: list[date], values: npt.NDArray[np.float64]) -> None:
        index = {month_day(d): i for i, d in enumerate(_LEAP_DAYS)}
        for d, v in zip(days, values, strict=True):
            if np.isfinite(v):
                self.sums[slug][index[month_day(d)]] += v
                self.counts[slug][index[month_day(d)]] += 1

    def normals(self, slug: str) -> dict[int, float]:
        """Smoothed daily normal (mm) for each calendar day, keyed by month*100 + day."""
        counts = self.counts[slug]
        if (counts == 0).any():
            raise ValueError(f"normal period incomplete for {slug}")
        daily = self.sums[slug] / counts
        half = SMOOTH_DAYS // 2
        padded = np.concatenate([daily[-half:], daily, daily[:half]])  # wrap around the year
        smooth = np.convolve(padded, np.ones(SMOOTH_DAYS) / SMOOTH_DAYS, mode="valid")
        return {month_day(d): float(v) for d, v in zip(_LEAP_DAYS, smooth, strict=True)}


RainRow = tuple[int, date, float | None, str]  # market_id, date, rain_mm, source


def rain_rows(
    market_id: int, days: list[date], values: npt.NDArray[np.float64], source: str
) -> list[RainRow]:
    return [
        (market_id, d, round(float(v), 2) if np.isfinite(v) else None, source)
        for d, v in zip(days, values, strict=True)
    ]


def write_daily(conn: Connection, rows: list[RainRow]) -> int:
    """Upsert daily rain rows in one statement. Real-time values never overwrite final ones."""
    if not rows:
        return 0
    result = conn.execute(
        text("""
            INSERT INTO rainfall_daily (market_id, date, rain_mm, source)
            SELECT * FROM unnest(CAST(:mids AS int[]), CAST(:dates AS date[]),
                                 CAST(:rains AS numeric[]), CAST(:sources AS varchar[]))
            ON CONFLICT (market_id, date) DO UPDATE
               SET rain_mm = EXCLUDED.rain_mm, source = EXCLUDED.source, ingested_at = now()
             WHERE rainfall_daily.source = 'imd_realtime' OR EXCLUDED.source = 'imd_final'
            """),
        {
            "mids": [r[0] for r in rows],
            "dates": [r[1] for r in rows],
            "rains": [r[2] for r in rows],
            "sources": [r[3] for r in rows],
        },
    )
    return int(result.rowcount or 0)


def write_normals(conn: Connection, market_id: int, normals: dict[int, float]) -> None:
    stmt = insert(RainfallNormal).values(
        [
            {"market_id": market_id, "month_day": md, "normal_mm": round(v, 2)}
            for md, v in normals.items()
        ]
    )
    conn.execute(
        stmt.on_conflict_do_update(
            index_elements=["market_id", "month_day"], set_={"normal_mm": stmt.excluded.normal_mm}
        )
    )


def _market_ids(conn: Connection) -> dict[str, int]:
    ids = {slug: id_ for slug, id_ in conn.execute(select(Market.slug, Market.id))}
    missing = set(MARKET_COORDS) - set(ids)
    if missing:
        raise RuntimeError(f"markets not synced yet (run price ingestion first): {sorted(missing)}")
    return ids


def _start_run(engine: Engine, job: str) -> int:
    with engine.begin() as conn:
        run_id: int = conn.execute(
            insert(IngestionRun).values(job=job, status="running").returning(IngestionRun.id)
        ).scalar_one()
    return run_id


def _finish(
    engine: Engine, run_id: int, status: str, fetched: int, written: int, error: str | None
) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(IngestionRun)
            .where(IngestionRun.id == run_id)
            .values(
                status=status,
                finished_at=datetime.now().astimezone(),
                rows_fetched=fetched,
                rows_inserted=written,
                error=error,
            )
        )


def run_backfill(engine: Engine, client: ImdClient, *, from_year: int, today: date) -> int:
    """Normals from 1991-2020, final daily data from ``from_year``, real-time for the rest."""
    masks = box_masks(MARKET_COORDS)
    run_id = _start_run(engine, "rainfall_backfill")
    fetched = written = 0
    try:
        with engine.connect() as conn:
            market_ids = _market_ids(conn)
        clim = Climatology.empty(masks)
        last_final: date | None = None
        years = sorted(set(NORMAL_YEARS) | set(range(from_year, today.year + 1)))
        for year in years:
            data = client.fetch_year(year)
            if data is None:
                logger.info("IMD %d: final data not published yet", year)
                continue
            days, grids = data
            fetched += len(days)
            last_final = days[-1]
            rows: list[RainRow] = []
            for slug, mask in masks.items():
                values = box_mean(grids, mask)
                if year in NORMAL_YEARS:
                    clim.add(slug, days, values)
                if year >= from_year:
                    rows += rain_rows(market_ids[slug], days, values, "imd_final")
            with engine.begin() as conn:
                written += write_daily(conn, rows)
            logger.info("IMD %d: %d days", year, len(days))

        with engine.begin() as conn:
            for slug in masks:
                write_normals(conn, market_ids[slug], clim.normals(slug))
        logger.info("Wrote normals for %d mandis", len(masks))

        start = (last_final + timedelta(days=1)) if last_final else date(from_year, 1, 1)
        f, w = _load_realtime(engine, client, masks, market_ids, start, today - timedelta(days=1))
        fetched, written = fetched + f, written + w
    except Exception as exc:
        _finish(engine, run_id, "failed", fetched, written, f"{type(exc).__name__}: {exc}"[:2000])
        raise
    _finish(engine, run_id, "success", fetched, written, None)
    return written


def run_recent(engine: Engine, client: ImdClient, *, days: int, today: date) -> int:
    """Weekly job: re-read the last ``days`` days from the real-time feed."""
    masks = box_masks(MARKET_COORDS)
    run_id = _start_run(engine, "ingest_rainfall")
    try:
        with engine.connect() as conn:
            market_ids = _market_ids(conn)
        end = today - timedelta(days=1)
        fetched, written = _load_realtime(
            engine, client, masks, market_ids, end - timedelta(days=days - 1), end
        )
    except Exception as exc:
        _finish(engine, run_id, "failed", 0, 0, f"{type(exc).__name__}: {exc}"[:2000])
        raise
    _finish(engine, run_id, "success", fetched, written, None)
    return written


def _load_realtime(
    engine: Engine,
    client: ImdClient,
    masks: dict[str, npt.NDArray[np.bool_]],
    market_ids: dict[str, int],
    start: date,
    end: date,
) -> tuple[int, int]:
    fetched = written = 0
    day = start
    while day <= end:
        grid = client.fetch_day(day)
        if grid is None:
            logger.info("IMD real-time %s not available", day)
        else:
            fetched += 1
            rows = [
                row
                for slug, mask in masks.items()
                for row in rain_rows(
                    market_ids[slug], [day], box_mean(grid[np.newaxis], mask), "imd_realtime"
                )
            ]
            with engine.begin() as conn:
                written += write_daily(conn, rows)
        day += timedelta(days=1)
    logger.info("IMD real-time %s..%s: %d days fetched", start, end, fetched)
    return fetched, written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    back = sub.add_parser("backfill", help="normals + history (one-time, ~1 GB download)")
    back.add_argument("--from-year", type=int, default=2019)
    recent = sub.add_parser("recent", help="re-read recent days (weekly job)")
    recent.add_argument("--days", type=int, choices=range(1, 61), metavar="1-60", default=21)
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)
    try:
        with ImdClient() as client:
            if args.mode == "backfill":
                n = run_backfill(get_engine(), client, from_year=args.from_year, today=today_ist())
            else:
                n = run_recent(get_engine(), client, days=args.days, today=today_ist())
    except Exception:
        logger.exception("Rainfall %s failed", args.mode)
        return 1
    logger.info("Rainfall %s done: %d rows written", args.mode, n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
