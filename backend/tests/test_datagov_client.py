"""DataGovClient: User-Agent, retries, fail-fast errors and pagination (no network)."""

from collections.abc import Callable
from datetime import date

import httpx
import pytest

from ingestion.datagov_client import USER_AGENT, DataGovClient, DataGovError

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler, sleeps: list[float] | None = None) -> DataGovClient:
    delays = sleeps if sleeps is not None else []
    return DataGovClient(
        "test-key",
        transport=httpx.MockTransport(handler),
        sleep=delays.append,
        max_retries=2,
    )


def _rec(day: str) -> dict[str, str]:
    return {"Market": "Kolar", "Arrival_Date": day}


def test_sends_custom_user_agent_and_filters() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"total": 1, "records": [_rec("01/01/2025")]})

    page = _client(handler).fetch_page({"State": "Karnataka"}, offset=0, limit=10)
    assert page.total == 1
    assert seen[0].headers["User-Agent"] == USER_AGENT
    assert seen[0].url.params["filters[State]"] == "Karnataka"
    assert seen[0].url.params["sort[Arrival_Date]"] == "desc"


def test_retries_retryable_status_with_backoff() -> None:
    calls = iter([502, 429, 200])

    def handler(_: httpx.Request) -> httpx.Response:
        status = next(calls)
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(200, json={"total": 0, "records": []})

    sleeps: list[float] = []
    _client(handler, sleeps).fetch_page({}, offset=0, limit=10)
    assert sleeps == [2.0, 4.0]


def test_gives_up_after_max_retries() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow")

    with pytest.raises(DataGovError, match="after 3 attempts"):
        _client(handler).fetch_page({}, offset=0, limit=10)


def test_non_retryable_error_fails_fast_without_leaking_key() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    with pytest.raises(DataGovError) as info:
        _client(handler).fetch_page({}, offset=0, limit=10)
    assert "test-key" not in str(info.value)
    assert info.value.__cause__ is None and info.value.__suppress_context__


def test_iter_records_pages_until_before_since() -> None:
    pages = {
        0: [_rec("10/01/2025"), _rec("09/01/2025")],
        2: [_rec("08/01/2025"), _rec("31/12/2024")],  # crosses `since` -> stop
        4: [_rec("01/12/2024"), _rec("30/11/2024")],
    }
    offsets: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        offset = int(req.url.params["offset"])
        offsets.append(offset)
        return httpx.Response(200, json={"total": 6, "records": pages[offset]})

    got = list(_client(handler).iter_records({}, since=date(2025, 1, 1), page_size=2))
    assert offsets == [0, 2]
    assert len(got) == 4


def test_iter_records_stops_on_short_page() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"total": 1, "records": [_rec("10/01/2025")]})

    assert len(list(_client(handler).iter_records({}, since=date(2020, 1, 1), page_size=5))) == 1
