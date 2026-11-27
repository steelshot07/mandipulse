"""Exploratory analysis behind docs/Findings.md. Exploration only: nothing here is imported by app code.

Run from backend/ (settings read backend/.env):  .venv/Scripts/python ../notebooks/eda.py
Reads the analytics views over DATABASE_URL (backend/.env) and prints the numbers.
Cells are marked with `# %%` so the file also opens as a notebook in VS Code/Jupyter.
"""

# %% Setup
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.db.session import get_engine  # noqa: E402

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 20)
engine = get_engine()
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def section(title: str) -> None:
    print(f"\n{'=' * 8} {title} {'=' * 8}")


weekly = pd.read_sql(
    """
    SELECT c.slug AS commodity, m.slug AS market, w.week_start, w.modal_price,
           w.modal_price_filled, w.is_gap, w.weeks_since_obs
      FROM v_prices_weekly w
      JOIN markets m ON m.id = w.market_id JOIN commodities c ON c.id = w.commodity_id
    """,
    engine,
    parse_dates=["week_start"],
)
weekly["year"] = weekly.week_start.dt.year
# Only complete calendar years for seasonal statistics.
full = weekly[(weekly.year >= 2019) & (weekly.year <= 2025)]

# %% 1. Coverage and gaps
section("1. Coverage (weeks, gaps, longest gap)")
cov = weekly.groupby(["commodity", "market"]).agg(
    first=("week_start", "min"),
    weeks=("week_start", "size"),
    gaps=("is_gap", "sum"),
    unfilled=("modal_price_filled", lambda s: s.isna().sum()),
    longest_gap=("weeks_since_obs", "max"),
)
cov["gap_pct"] = (100 * cov.gaps / cov.weeks).round(1)
print(cov.to_string())
print(f"\nOverall: {cov.gaps.sum()} gap weeks of {cov.weeks.sum()} ({100 * cov.gaps.sum() / cov.weeks.sum():.1f}%), "
      f"{cov.unfilled.sum()} left unfilled after the 2-week rule")

# %% 2. Seasonality: average month index (price / that year's average), 2019-2025
section("2. Seasonality (avg price index by month, 1.00 = year average)")
monthly = (
    full.dropna(subset=["modal_price"])
    .assign(month=lambda d: d.week_start.dt.month)
    .groupby(["commodity", "market", "year", "month"]).modal_price.mean()
    .reset_index()
)
monthly["index"] = monthly.modal_price / monthly.groupby(["commodity", "market", "year"]).modal_price.transform("mean")
profile = monthly.groupby(["commodity", "month"])["index"].mean().unstack()
profile.columns = MONTHS
print(profile.round(2).to_string())
for com, row in profile.iterrows():
    lo, hi = row.idxmin(), row.idxmax()
    print(f"  {com}: trough {lo} ({row[lo]:.2f}), peak {hi} ({row[hi]:.2f}), peak/trough {row[hi] / row[lo]:.1f}x")
# How consistent is the onion peak? Share of market-years whose max month is Sep-Dec.
peak_month = monthly.loc[monthly.groupby(["commodity", "market", "year"])["index"].idxmax()]
share = peak_month.groupby("commodity").month.apply(lambda m: (m >= 9).mean())
print("  share of market-years peaking Sep-Dec:", share.round(2).to_dict())

# %% 3. Volatility by commodity and market (last 52 weeks + whole history)
section("3. Volatility")
weekly = weekly.sort_values(["commodity", "market", "week_start"])
weekly["chg"] = weekly.groupby(["commodity", "market"]).modal_price.pct_change(fill_method=None)
last52 = weekly[weekly.week_start > weekly.week_start.max() - pd.Timedelta(weeks=52)]
vol = last52.groupby(["commodity", "market"]).agg(
    cv_52w=("modal_price", lambda s: s.std() / s.mean()),
    mean_abs_wk_chg=("chg", lambda s: s.abs().mean()),
)
vol["cv_all"] = weekly.groupby(["commodity", "market"]).modal_price.agg(lambda s: s.std() / s.mean())
print(vol.round(3).to_string())
print("\nMedian by commodity:")
print(vol.groupby("commodity").median().round(3).to_string())
big = weekly.groupby("commodity").chg.apply(lambda s: (s.abs() > 0.25).mean())
print("Share of weeks with a >25% week-on-week move:", (100 * big).round(1).to_dict())

# %% 4. Biggest 4-week price surges (whole history)
section("4. Biggest 4-week surges")
weekly["chg4"] = weekly.groupby(["commodity", "market"]).modal_price_filled.pct_change(4, fill_method=None)
top = weekly.dropna(subset=["chg4"]).sort_values("chg4", ascending=False).groupby("commodity").head(3)
print(top[["commodity", "market", "week_start", "modal_price_filled", "chg4"]].round(2).to_string(index=False))

# %% 5. Do markets of the same commodity move together? (weekly % changes)
section("5. Co-movement between markets (correlation of weekly % changes)")
for com, grp in weekly.groupby("commodity"):
    wide = grp.pivot(index="week_start", columns="market", values="chg")
    corr = wide.corr(min_periods=100)
    off = corr.where(~np.eye(len(corr), dtype=bool)).stack()
    print(f"  {com}: median pairwise r = {off.median():.2f} (min {off.min():.2f}, max {off.max():.2f})")
nashik = ["lasalgaon", "lasalgaon-niphad", "lasalgaon-vinchur", "pimpalgaon-baswant",
          "pimpalgaon-saykheda", "nashik", "manmad"]
onion = weekly[weekly.commodity == "onion"].pivot(index="week_start", columns="market", values="chg")
inner = onion[nashik].corr(min_periods=100).where(~np.eye(len(nashik), dtype=bool)).stack().median()
outer = onion[nashik].corrwith(onion["bengaluru"], drop=True).median()
print(f"  onion: Nashik-cluster pairs r = {inner:.2f}; Nashik markets vs Bengaluru r = {outer:.2f}")

# %% 6. Rainfall deviation vs later price change (lags 0-12 weeks)
section("6. Rainfall deviation vs 4-week price change")
rain = pd.read_sql(
    """
    SELECT m.slug AS market, r.week_start, r.deviation_mm, r.rain_mm, r.normal_mm, r.n_days
      FROM v_rainfall_weekly r JOIN markets m ON m.id = r.market_id
    """,
    engine,
    parse_dates=["week_start"],
)
if rain.empty:
    print("  (no rainfall loaded yet)")
else:
    rain = rain[rain.n_days == 7].sort_values(["market", "week_start"])
    rain["dev4"] = rain.groupby("market").deviation_mm.transform(lambda s: s.rolling(4).sum())
    annual = rain[rain.week_start.dt.year.between(2019, 2025)].groupby(
        [rain.market, rain.week_start.dt.year]).agg(rain=("rain_mm", "sum"), normal=("normal_mm", "sum"))
    annual["pct_of_normal"] = (100 * annual.rain / annual.normal).round(0)
    print("Annual rainfall as % of 1991-2020 normal (selected mandis):")
    print(annual.pct_of_normal.unstack().loc[["lasalgaon", "kolar", "madanapalle", "agra", "kolkata-bara-bazar"]].to_string())
    rows = []
    for (com, mkt), grp in weekly.groupby(["commodity", "market"]):
        g = grp.set_index("week_start").chg4
        r = rain[rain.market == mkt].set_index("week_start").dev4
        for lag in range(0, 13):
            pair = pd.concat([r, g.shift(-lag, freq="7D")], axis=1, join="inner").dropna()
            if len(pair) > 30:
                rows.append((com, mkt, lag, pair.corr().iloc[0, 1], len(pair)))
    lagdf = pd.DataFrame(rows, columns=["commodity", "market", "lag", "r", "n"])
    lagdf["sig"] = lagdf.r.abs() > 1.96 / np.sqrt(lagdf.n)
    best = lagdf.loc[lagdf.groupby(["commodity", "market"]).r.apply(lambda s: s.abs().idxmax())]
    print("\nStrongest lag per series:")
    print(best.round(3).to_string(index=False))
    print(f"\nSignificant (|r| > 1.96/sqrt(n)) at any lag: {best.sig.sum()} of {len(best)} series; "
          f"significant (series, lag) pairs: {lagdf.sig.sum()} of {len(lagdf)} "
          f"(~{0.05 * len(lagdf):.0f} expected by chance)")
    print("Median r by lag and commodity:")
    print(lagdf.pivot_table(index="commodity", columns="lag", values="r", aggfunc="median").round(2).to_string())
