"""Tests for rate limiting, security headers, generic errors and the CORS guard."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.routes.health import get_db_checker
from app.core.config import Settings
from app.core.security import RateLimiter
from app.main import create_app


def _client(limiter: RateLimiter | None = None) -> TestClient:
    app = create_app(limiter)

    def _checker() -> Callable[[], bool]:
        return lambda: True

    app.dependency_overrides[get_db_checker] = _checker

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret detail: postgresql://user:pw@host/db")

    return TestClient(app, raise_server_exceptions=False)


def test_rate_limiter_blocks_after_limit_and_resets() -> None:
    now = [0.0]
    limiter = RateLimiter(limit=2, window_seconds=60, clock=lambda: now[0])
    assert limiter.hit("1.2.3.4") is None
    assert limiter.hit("1.2.3.4") is None
    assert limiter.hit("1.2.3.4") == pytest.approx(60)
    assert limiter.hit("5.6.7.8") is None  # other IPs unaffected
    now[0] = 61
    assert limiter.hit("1.2.3.4") is None


def test_api_returns_429_with_error_body_when_limited() -> None:
    client = _client(RateLimiter(limit=1))
    assert client.get("/health").status_code == 200
    resp = client.get("/health")
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limited"
    assert "Retry-After" in resp.headers


def test_security_headers_present() -> None:
    resp = _client().get("/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Content-Security-Policy"].startswith("default-src 'none'")


def test_unexpected_error_is_generic_and_hides_details() -> None:
    resp = _client().get("/boom")
    assert resp.status_code == 500
    assert resp.json() == {"error": {"code": "internal_error", "message": "Something went wrong."}}
    assert "postgresql" not in resp.text


def test_unknown_route_uses_standard_error_body() -> None:
    resp = _client().get("/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_wildcard_cors_refused_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(env="production", allowed_origins="*")  # type: ignore[arg-type]
