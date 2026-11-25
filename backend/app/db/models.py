"""SQLAlchemy ORM models. Tables are added from Phase 1 onward."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base shared by all models and used by Alembic autogenerate."""
