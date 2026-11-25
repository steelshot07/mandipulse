# PRD — MandiPulse

> Working name. Live mandi price intelligence + short-term price forecasting for Indian vegetables.

## 1. Problem

Wholesale prices of perishable vegetables (onion, tomato, potato) in Indian mandis swing sharply week to week. Farmers and small traders usually learn the price only on the day they reach the mandi, so they can't decide *when* or *where* to sell. Price data is public (Agmarknet / data.gov.in), but it is raw, gappy and hard to read, and almost no public tool tells you **where prices are heading, why, and how accurate past forecasts were**.

## 2. Goal

Build a live, publicly accessible web app that:

1. Ingests mandi prices daily from government sources.
2. Shows clean price history, volatility and seasonality (analytics).
3. Forecasts weekly modal prices 1–4 weeks ahead, with uncertainty bands.
4. Explains the main drivers behind each forecast.
5. Publishes its own forecast-vs-actual accuracy, updated live.
6. Sends price-movement alerts via Telegram.

Secondary goal: serve as a portfolio project for SDE, ML engineer, and data analytics roles. Every feature should be demonstrable in an interview.

## 3. Target users

| User | Need | What they use |
|---|---|---|
| Farmer / FPO member | "Should I sell this week or wait? Which nearby mandi pays more?" | Mobile dashboard, Telegram alerts |
| Small trader / aggregator | Price trends across mandis, early warning of spikes/crashes | Dashboard, compare view |
| Analyst / student / journalist | Clean historical data, volatility & seasonality insights | Analytics pages, CSV export |
| Recruiter / interviewer | Proof the system works and is honest about accuracy | Accuracy page, README |

## 4. Scope (v1)

- **Commodities:** Onion, Tomato, Potato.
- **Markets:** ~10 major mandis per commodity (initial candidates: Lasalgaon, Pimpalgaon, Indore, Bengaluru for onion; Kolar, Madanapalle, Azadpur for tomato; Agra, Azadpur, Kolkata for potato). Verify exact market names in the data before fixing the list.
- **Granularity:** Data stored daily, forecasts made weekly (weekly modal price, ₹/quintal).
- **Horizon:** 1, 2, 3 and 4 weeks ahead.
- **Language:** English UI in v1; layout must allow Hindi later.

### Out of scope for v1
- User accounts / login (dashboard is public; Telegram subscription needs no login).
- All-India, all-commodity coverage.
- Buying/selling or any transactions.
- Native mobile app.

## 5. Features

### F1. Data ingestion (must have)
- Daily pull from the data.gov.in mandi price API.
- One-time historical backfill from CEDA (Ashoka) Agmarknet downloads.
- Daily/annual rainfall from IMD gridded data, aggregated to district level.
- Ingestion log (rows fetched, rows inserted, failures) visible on a status page.

### F2. Price explorer (must have)
- Select commodity + mandi → daily and weekly modal price chart with min–max band.
- Compare up to 4 mandis on one chart.
- Shows "last updated" date for every series.

### F3. Analytics insights (must have)
- Volatility by mandi (coefficient of variation, rolling 4-week std).
- Seasonality heatmap (month × year).
- Price reaction to rainfall deviation (lagged correlation chart).
- 3–5 written key findings, refreshed manually per release.

### F4. Forecasts (must have)
- Weekly modal price forecast for 1–4 weeks, with P10/P50/P90 band.
- Signal: **Rising / Stable / Falling**, with threshold (e.g. ±10% vs current).
- "Why" panel: top drivers (e.g. lagged arrivals, rainfall deviation, seasonality).

### F5. Accuracy page (must have — key differentiator)
- Every published forecast is stored and later compared with the actual price.
- Shows MAPE and MASE per commodity/horizon, versus a seasonal-naive baseline.
- Chart of past forecasts vs actuals.

### F6. Best-mandi suggestion (should have)
- Given a district, rank nearby mandis by forecast price minus estimated transport cost (simple per-km cost assumption, clearly labelled).

### F7. Telegram alerts (should have)
- `/subscribe onion lasalgaon` → weekly digest + alert when forecast move > threshold.
- `/unsubscribe`, `/price onion lasalgaon`.

### F8. Data export (could have)
- Download cleaned weekly series as CSV.

## 6. Success metrics

- Forecast beats seasonal-naive baseline (MASE < 1) on at least 2 of 3 commodities at the 1-week horizon in backtest.
- Daily ingestion succeeds on ≥ 95% of days over a month.
- Dashboard loads in < 2 s on mobile 4G.
- At least 10 real Telegram subscribers (stretch).

## 7. Constraints

- Free tiers only (Supabase/Neon, Render, Vercel, GitHub Actions).
- Government APIs can be slow, late or down — the app must degrade gracefully and always show data freshness.
- Must never present forecasts as guarantees; show uncertainty and a disclaimer.

## 8. Open questions

- Exact data.gov.in resource and fields available (check whether arrivals quantity is included or only prices; CEDA has arrivals).
- Transport cost assumption for F6.
- Whether to add a Power BI / Metabase analytics view alongside the React app.
