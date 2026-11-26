"""Lambda handler: argument validation and error reporting (loader stubbed)."""

from datetime import date
from typing import Any

import pytest

from ingestion import lambda_handler
from ingestion.lambda_handler import IngestionFailedError, handler


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    seen: list[tuple[Any, ...]] = []

    def fake_run_cli(job: str, since: date, page_size: int) -> int:
        seen.append((job, since, page_size))
        return 0

    monkeypatch.setattr(lambda_handler, "run_cli", fake_run_cli)
    monkeypatch.setattr(lambda_handler, "today_ist", lambda: date(2026, 11, 27))
    return seen


def test_default_window_is_ten_days(calls: list[tuple[Any, ...]]) -> None:
    assert handler({}, None) == {"status": "success"}
    assert calls == [("ingest_daily", date(2026, 11, 18), 2_000)]


def test_custom_days(calls: list[tuple[Any, ...]]) -> None:
    handler({"days": 3}, None)
    assert calls[0][1] == date(2026, 11, 25)


@pytest.mark.parametrize("days", [0, 61, "10", True, 2.5])
def test_rejects_bad_days(calls: list[tuple[Any, ...]], days: object) -> None:
    with pytest.raises(ValueError):
        handler({"days": days}, None)
    assert calls == []


def test_failed_run_raises_so_lambda_reports_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lambda_handler, "run_cli", lambda *a, **k: 1)
    with pytest.raises(IngestionFailedError):
        handler({}, None)
