"""Database engine and session factory."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create the engine lazily so importing the app never needs a database."""
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return create_engine(
        settings.sqlalchemy_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is always closed."""
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    with factory() as session:
        yield session
