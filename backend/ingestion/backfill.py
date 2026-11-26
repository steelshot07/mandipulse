"""One-time historical backfill: ``python -m ingestion.backfill [--since YYYY-MM-DD]``."""

import argparse
import sys
from datetime import date

from app.core.markets import BACKFILL_START
from ingestion.loader import run_cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since",
        type=date.fromisoformat,
        default=BACKFILL_START,
        help=f"earliest arrival date to load (default {BACKFILL_START})",
    )
    args = parser.parse_args(argv)
    return run_cli("backfill", args.since, page_size=10_000)


if __name__ == "__main__":
    sys.exit(main())
