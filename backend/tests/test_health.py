"""Tests for GET /health (database check is stubbed; no real DB needed)."""

from collections.abc import Callable

from fastapi.testclient import TestClient

from app.api.routes.health import get_db_checker
from app.main import create_app


def _client(db_ok: bool) -> TestClient:
    app = create_app()

    def _checker() -> Callable[[], bool]:
        return lambda: db_ok

    app.dependency_overrides[get_db_checker] = _checker
    return TestClient(app)


def test_health_ok() -> None:
    resp = _client(db_ok=True).get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok"}


def test_health_db_down_returns_503() -> None:
    resp = _client(db_ok=False).get("/health")
    assert resp.status_code == 503
    assert resp.json() == {"status": "degraded", "db": "error"}
