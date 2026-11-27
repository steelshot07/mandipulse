"""Rainfall tables and the cleaning/analytics views.

Price views (docs/Architecture.md §3):
- v_prices_clean (materialized): every raw report plus an outlier flag. A report is an
  outlier if its modal price is outside [min, max], or more than 5x (or under 1/5) the median
  modal price of the same market x commodity over the previous 28 days (needs >= 5 reports).
- v_prices_weekly (materialized): one row per market x commodity x ISO week (Monday start)
  for every week between the series' first and last report, so gaps are explicit rows.
  modal_price = median of the week's non-outlier daily modal prices (all varieties);
  modal_price_filled carries the last value forward for gaps of at most 2 weeks, longer
  gaps stay NULL. Both refresh after every ingestion run (ingestion/analytics.py).
- v_volatility, v_seasonality, v_rainfall_weekly: plain views on top.

Rainfall: rainfall_daily holds the mean IMD 0.25 deg gridded rainfall over a box of
+/- 0.5 deg around each mandi; rainfall_normals holds the 1991-2020 daily climatology for
the same box, keyed by month*100 + day (so 29 Feb has its own normal).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRICES_CLEAN = """
CREATE MATERIALIZED VIEW v_prices_clean AS
WITH base AS (
    SELECT r.id, r.market_id, r.commodity_id, r.variety, r.grade, r.arrival_date,
           r.min_price, r.max_price, r.modal_price,
           (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY p.modal_price)
              FROM raw_prices p
             WHERE p.market_id = r.market_id
               AND p.commodity_id = r.commodity_id
               AND p.arrival_date >= r.arrival_date - 28
               AND p.arrival_date < r.arrival_date
            HAVING count(*) >= 5) AS trailing_median
      FROM raw_prices r
), flagged AS (
    SELECT base.*,
           CASE
             WHEN modal_price < min_price OR modal_price > max_price
               THEN 'modal_outside_min_max'
             WHEN trailing_median IS NOT NULL
                  AND (modal_price > 5 * trailing_median OR modal_price * 5 < trailing_median)
               THEN 'over_5x_from_28d_median'
           END AS outlier_reason
      FROM base
)
SELECT flagged.*, outlier_reason IS NOT NULL AS is_outlier FROM flagged
"""

PRICES_WEEKLY = """
CREATE MATERIALIZED VIEW v_prices_weekly AS
WITH obs AS (
    SELECT market_id, commodity_id, date_trunc('week', arrival_date)::date AS week_start,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY modal_price) AS modal_price,
           min(min_price) AS min_price,
           max(max_price) AS max_price,
           count(*) AS n_reports,
           count(DISTINCT arrival_date) AS n_days
      FROM v_prices_clean
     WHERE NOT is_outlier
     GROUP BY 1, 2, 3
), bounds AS (
    SELECT market_id, commodity_id, min(week_start) AS first_week, max(week_start) AS last_week
      FROM obs GROUP BY 1, 2
), calendar AS (
    SELECT b.market_id, b.commodity_id, gs::date AS week_start
      FROM bounds b, generate_series(b.first_week, b.last_week, interval '7 days') AS gs
), joined AS (
    SELECT c.market_id, c.commodity_id, c.week_start,
           o.modal_price, o.min_price, o.max_price,
           coalesce(o.n_reports, 0) AS n_reports, coalesce(o.n_days, 0) AS n_days,
           count(o.modal_price) OVER (PARTITION BY c.market_id, c.commodity_id
                                      ORDER BY c.week_start) AS run_id
      FROM calendar c
      LEFT JOIN obs o USING (market_id, commodity_id, week_start)
), runs AS (
    SELECT joined.*,
           row_number() OVER (PARTITION BY market_id, commodity_id, run_id
                              ORDER BY week_start) - 1 AS weeks_since_obs,
           first_value(modal_price) OVER (PARTITION BY market_id, commodity_id, run_id
                                          ORDER BY week_start) AS last_obs_price
      FROM joined
)
SELECT market_id, commodity_id, week_start, modal_price, min_price, max_price,
       n_reports, n_days,
       modal_price IS NULL AS is_gap,
       weeks_since_obs::int AS weeks_since_obs,
       CASE WHEN weeks_since_obs <= 2 THEN last_obs_price END AS modal_price_filled
  FROM runs
"""

VOLATILITY = """
CREATE VIEW v_volatility AS
SELECT market_id, commodity_id, week_start, modal_price, modal_price_filled,
       stddev_samp(modal_price) OVER w4 AS rolling_std_4w,
       avg(modal_price) OVER w4 AS rolling_mean_4w,
       count(modal_price) OVER w4 AS n_obs_4w,
       modal_price / NULLIF(lag(modal_price) OVER w, 0) - 1 AS pct_change_1w,
       modal_price_filled / NULLIF(lag(modal_price_filled, 4) OVER w, 0) - 1 AS pct_change_4w
  FROM v_prices_weekly
WINDOW w AS (PARTITION BY market_id, commodity_id ORDER BY week_start),
       w4 AS (PARTITION BY market_id, commodity_id ORDER BY week_start
              ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
"""

SEASONALITY = """
CREATE VIEW v_seasonality AS
WITH monthly AS (
    SELECT market_id, commodity_id,
           extract(year FROM week_start)::int AS year,
           extract(month FROM week_start)::int AS month,
           avg(modal_price) AS avg_price,
           count(modal_price) AS n_weeks
      FROM v_prices_weekly
     WHERE modal_price IS NOT NULL
     GROUP BY 1, 2, 3, 4
)
SELECT monthly.*,
       avg_price / NULLIF(avg(avg_price) OVER (PARTITION BY market_id, commodity_id, year), 0)
         AS index_vs_year_avg
  FROM monthly
"""

RAINFALL_WEEKLY = """
CREATE VIEW v_rainfall_weekly AS
SELECT d.market_id,
       date_trunc('week', d.date)::date AS week_start,
       sum(d.rain_mm) AS rain_mm,
       sum(n.normal_mm) AS normal_mm,
       sum(d.rain_mm) - sum(n.normal_mm) AS deviation_mm,
       count(*) AS n_days
  FROM rainfall_daily d
  JOIN rainfall_normals n
    ON n.market_id = d.market_id
   AND n.month_day = extract(month FROM d.date)::int * 100 + extract(day FROM d.date)::int
 GROUP BY 1, 2
"""


def upgrade() -> None:
    # Speeds up the trailing-median lookup in v_prices_clean.
    op.create_index(
        "ix_raw_prices_series_date", "raw_prices", ["market_id", "commodity_id", "arrival_date"]
    )

    op.create_table(
        "rainfall_daily",
        sa.Column("market_id", sa.Integer(), sa.ForeignKey("markets.id"), primary_key=True),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("rain_mm", sa.Numeric(7, 2), nullable=True),  # NULL if every cell is missing
        sa.Column("source", sa.String(16), nullable=False),  # imd_final | imd_realtime
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "rainfall_normals",
        sa.Column("market_id", sa.Integer(), sa.ForeignKey("markets.id"), primary_key=True),
        sa.Column("month_day", sa.SmallInteger(), primary_key=True),  # e.g. 1231, 229
        sa.Column("normal_mm", sa.Numeric(7, 2), nullable=False),
    )
    for table in ("rainfall_daily", "rainfall_normals"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

    op.execute(PRICES_CLEAN)
    op.execute("CREATE UNIQUE INDEX ux_v_prices_clean_id ON v_prices_clean (id)")
    op.execute(PRICES_WEEKLY)
    op.execute(
        "CREATE UNIQUE INDEX ux_v_prices_weekly_key "
        "ON v_prices_weekly (market_id, commodity_id, week_start)"
    )
    op.execute(VOLATILITY)
    op.execute(SEASONALITY)
    op.execute(RAINFALL_WEEKLY)
    # Materialized views are reachable through Supabase's Data API and can't use RLS, so
    # revoke the public API roles (they exist only on Supabase).
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON v_prices_clean, v_prices_weekly, v_volatility, v_seasonality,
                          v_rainfall_weekly FROM anon, authenticated;
          END IF;
        END $$;
        """)


def downgrade() -> None:
    for view in ("v_rainfall_weekly", "v_seasonality", "v_volatility"):
        op.execute(f"DROP VIEW IF EXISTS {view}")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS v_prices_weekly")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS v_prices_clean")
    op.drop_table("rainfall_normals")
    op.drop_table("rainfall_daily")
    op.drop_index("ix_raw_prices_series_date", table_name="raw_prices")
