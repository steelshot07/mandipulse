"""Client for the data.gov.in mandi price resource (docs/Architecture.md §6a)."""

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

RESOURCE_ID = "35985678-0d79-46b4-9ed6-6f13308a1d24"
BASE_URL = "https://api.data.gov.in/resource/"
# Python's default User-Agent gets HTTP 502 from data.gov.in, so always send our own.
USER_AGENT = "mandipulse/0.1 (+https://github.com/steelshot07/mandipulse)"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

Record = dict[str, Any]


class DataGovError(RuntimeError):
    """Raised when the API still fails after all retries."""


@dataclass(frozen=True)
class Page:
    """One page of API results."""

    records: list[Record]
    total: int


class DataGovClient:
    """Fetch pages with timeout, retries + exponential backoff, and pagination."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ValueError("DATAGOV_API_KEY is not set")
        self._api_key = api_key
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=BASE_URL,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            transport=transport,
        )

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()

    def __enter__(self) -> "DataGovClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch_page(self, filters: dict[str, str], *, offset: int, limit: int) -> Page:
        """Fetch one page, newest arrival date first."""
        params: dict[str, str | int] = {
            "api-key": self._api_key,
            "format": "json",
            "offset": offset,
            "limit": limit,
            "sort[Arrival_Date]": "desc",
        }
        params.update({f"filters[{k}]": v for k, v in filters.items()})

        for attempt in range(self._max_retries + 1):
            try:
                resp = self._http.get(RESOURCE_ID, params=params)
                if resp.status_code not in RETRYABLE_STATUS:
                    resp.raise_for_status()
                    body = resp.json()
                    return Page(records=list(body.get("records", [])), total=int(body["total"]))
                problem = f"HTTP {resp.status_code}"
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                problem = type(exc).__name__
            except httpx.HTTPStatusError as exc:
                # Non-retryable (e.g. 400/403): fail fast. Never log the URL: it contains the key.
                raise DataGovError(f"HTTP {exc.response.status_code} from data.gov.in") from None

            if attempt == self._max_retries:
                raise DataGovError(f"data.gov.in failed after {attempt + 1} attempts: {problem}")
            delay = self._backoff_base * 2**attempt
            logger.warning("data.gov.in %s (offset=%d), retrying in %.0fs", problem, offset, delay)
            self._sleep(delay)
        raise AssertionError("unreachable")

    def iter_records(
        self, filters: dict[str, str], *, since: date, page_size: int = 10_000
    ) -> Iterator[Record]:
        """Yield records newest-first until arrival dates fall before ``since``.

        Newest-first paging is safe on a live dataset: rows added mid-run shift pages
        forward, which re-reads a few rows (handled by upsert) but never skips any.
        """
        offset = 0
        while True:
            page = self.fetch_page(filters, offset=offset, limit=page_size)
            if not page.records:
                return
            yield from page.records
            oldest = parse_source_date(page.records[-1].get("Arrival_Date"))
            if len(page.records) < page_size or (oldest is not None and oldest < since):
                return
            offset += page_size


def parse_source_date(value: object) -> date | None:
    """Parse the source's dd/mm/yyyy date; None if missing or malformed."""
    try:
        return datetime.strptime(str(value).strip(), "%d/%m/%Y").date()
    except ValueError:
        return None
