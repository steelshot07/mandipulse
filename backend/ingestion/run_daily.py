"""Daily ingestion job: ``python -m ingestion.run_daily [--days N]``.

Runs from GitHub Actions at 20:00 IST (.github/workflows/ingest.yml). Each run re-reads the
last ``--days`` days, not just yesterday, because mandis often report a few days late.
Re-reading is free: inserts are idempotent, so rows already stored are skipped.
Exits non-zero on failure so the workflow run is marked failed.
"""

import argparse
import sys
from datetime import date, timedelta

from app.core.time import today_ist
from ingestion.loader import run_cli

DEFAULT_LOOKBACK_DAYS = 10
# One page per query almost always covers 10 days; more pages are fetched if needed.
PAGE_SIZE = 2_000


def since_for(today: date, days: int) -> date:
    """First arrival date to load so the window covers ``days`` days up to ``today``."""
    return today - timedelta(days=days - 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--days",
        type=int,
        choices=range(1, 61),
        metavar="1-60",
        default=DEFAULT_LOOKBACK_DAYS,
        help=f"how many recent days to re-read (default {DEFAULT_LOOKBACK_DAYS})",
    )
    args = parser.parse_args(argv)
    return run_cli("ingest_daily", since_for(today_ist(), args.days), page_size=PAGE_SIZE)


if __name__ == "__main__":
    sys.exit(main())
