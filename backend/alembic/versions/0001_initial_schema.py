"""Initial schema: markets, commodities, raw_prices, ingestion_runs, quarantine_rows.

Row Level Security is enabled with no policies on every table, so Supabase's public
Data API (anon/authenticated roles) can't read or write them. The backend connects as
the table owner, which bypasses RLS (docs/Rules.md §6).

Revision ID: 0001
Revises:
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("markets", "commodities", "raw_prices", "ingestion_runs", "quarantine_rows")


def upgrade() -> None:
    op.create_table(
        "markets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("market_name", sa.String(128), nullable=False),
        sa.Column("state", sa.String(64), nullable=False),
        sa.Column("district", sa.String(64), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("census_district", sa.String(64), nullable=True),
    )
    op.create_table(
        "commodities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False, server_default="₹/quintal"),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job", sa.String(64), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("rows_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_quarantined", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_table(
        "raw_prices",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("market_id", sa.Integer(), sa.ForeignKey("markets.id"), nullable=False),
        sa.Column("commodity_id", sa.Integer(), sa.ForeignKey("commodities.id"), nullable=False),
        sa.Column("variety", sa.String(64), nullable=False),
        sa.Column("grade", sa.String(32), nullable=False),
        sa.Column("arrival_date", sa.Date(), nullable=False),
        sa.Column("min_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("max_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("modal_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("arrivals_tonnes", sa.Numeric(14, 2), nullable=True),
        sa.Column("source_market_name", sa.String(128), nullable=False),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "source",
            "market_id",
            "commodity_id",
            "variety",
            "grade",
            "arrival_date",
            "min_price",
            "max_price",
            "modal_price",
            name="uq_raw_prices_key",
        ),
    )
    op.create_index("ix_raw_prices_market_id", "raw_prices", ["market_id"])
    op.create_index("ix_raw_prices_commodity_id", "raw_prices", ["commodity_id"])
    op.create_index("ix_raw_prices_arrival_date", "raw_prices", ["arrival_date"])
    op.create_table(
        "quarantine_rows",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "ingestion_run_id", sa.Integer(), sa.ForeignKey("ingestion_runs.id"), nullable=True
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
