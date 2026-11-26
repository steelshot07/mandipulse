"""AWS Lambda entry point for the daily ingestion job (runs in ap-south-1, Mumbai).

data.gov.in only accepts connections from Indian IPs, so the job can't run on GitHub-hosted
runners (docs/Challenges.md #1). EventBridge Scheduler invokes this daily at 20:00 IST with
``{"days": 10}``. A failed run raises, so Lambda reports an error and the CloudWatch alarm fires.
"""

from typing import Any

from app.core.time import today_ist
from ingestion.loader import run_cli
from ingestion.run_daily import DEFAULT_LOOKBACK_DAYS, PAGE_SIZE, since_for


class IngestionFailedError(RuntimeError):
    """The run failed; details are in the logs and in ingestion_runs."""


def handler(event: dict[str, Any] | None, context: object) -> dict[str, str]:
    days = (event or {}).get("days", DEFAULT_LOOKBACK_DAYS)
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 60:
        raise ValueError("'days' must be an integer from 1 to 60")
    if run_cli("ingest_daily", since_for(today_ist(), days), page_size=PAGE_SIZE) != 0:
        raise IngestionFailedError("ingest_daily failed; see CloudWatch logs and ingestion_runs")
    return {"status": "success"}
