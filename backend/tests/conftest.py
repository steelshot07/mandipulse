"""Shared fixtures. DB tests use a disposable Postgres at TEST_DATABASE_URL (CI only)."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def migrated_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    if not TEST_DB:
        pytest.skip("TEST_DATABASE_URL not set")
    from alembic.config import Config

    from alembic import command
    from app.core.config import get_settings

    monkeypatch.setenv("DATABASE_URL", TEST_DB)
    get_settings.cache_clear()
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")
    try:
        yield get_settings().sqlalchemy_url
    finally:
        command.downgrade(cfg, "base")
        get_settings.cache_clear()
