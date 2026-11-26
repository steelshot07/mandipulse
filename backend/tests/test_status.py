"""GET /status/ingestion route (database replaced by a fake provider)."""

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from app.api.routes.status import get_status_provider
from app.main import create_app
from app.schemas.status import IngestionRunOut, IngestionStatusResponse, SeriesFreshness

STARTED = datetime(2026, 11, 26, 14, 30, tzinfo=UTC)
FAKE = IngestionStatusResponse(
    last_success_at=STARTED,
    stale_after_days=7,
    runs=[
        IngestionRunOut(
            id=3,
            job="ingest_daily",
            status="failed",
            started_at=STARTED,
            finished_at=STARTED,
            rows_fetched=10,
            rows_inserted=0,
            rows_quarantined=0,
        )
    ],
    series=[
        SeriesFreshness(
            commodity="onion",
            market="lasalgaon",
            market_name="Lasalgaon",
            last_arrival_date=date(2026, 11, 25),
            days_since=1,
            stale=False,
        )
    ],
)


def _client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_status_provider] = lambda: lambda: FAKE
    return TestClient(app)


def test_status_returns_runs_and_series_with_cache_header() -> None:
    resp = _client().get("/status/ingestion")
    assert resp.status_code == 200
    body = resp.json()
    assert body["runs"][0]["status"] == "failed"
    assert body["series"][0] == {
        "commodity": "onion",
        "market": "lasalgaon",
        "market_name": "Lasalgaon",
        "last_arrival_date": "2026-11-25",
        "days_since": 1,
        "stale": False,
    }
    assert resp.headers["Cache-Control"] == "public, max-age=300"


def test_status_never_exposes_run_error_text() -> None:
    body = _client().get("/status/ingestion").json()
    assert "error" not in body["runs"][0]


def test_status_is_read_only() -> None:
    assert _client().post("/status/ingestion").status_code == 405
