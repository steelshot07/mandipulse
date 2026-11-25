# Architecture — MandiPulse

## 1. High-level flow

```
 data.gov.in API ─┐
 CEDA backfill ───┼─► [Ingestion jobs] ─► raw tables (Postgres)
 IMD rainfall ────┘                              │
                                                 ▼
                                   [SQL cleaning views]  ← dedupe, outliers, weekly agg
                                                 │
                                                 ▼
                                   [Feature builder] ─► features table
                                                 │
                         weekly ─────────────────▼
                                   [Train + Predict] ─► forecasts table (versioned)
                                                 │
                         weekly ─────────────────▼
                                   [Evaluate] ─► forecast_accuracy table
                                                 │
                                                 ▼
                                         [FastAPI backend]
                                          │            │
                                          ▼            ▼
                                 [React dashboard]  [Telegram bot]
```

Scheduled jobs:
| Job | Schedule (IST) | What it does |
|---|---|---|
| `ingest_daily` | Daily 20:00 | Pull latest mandi prices, upsert raw rows, log run |
| `ingest_rainfall` | Weekly Mon 06:00 | Update district rainfall series |
| `retrain_and_forecast` | Weekly Mon 07:00 | Rebuild features, retrain, write new forecasts |
| `evaluate` | Weekly Mon 07:30 | Score matured forecasts against actuals |
| `send_alerts` | Weekly Mon 08:00 | Telegram digests + threshold alerts |

Jobs run on GitHub Actions cron (free) and call Python entry points directly; they don't go through the API.

## 2. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11 | ML + backend in one language |
| API | FastAPI + Pydantic v2 | Already familiar, typed, auto docs |
| DB | PostgreSQL (Supabase or Neon free tier) | SQL views for analytics, free hosting |
| ORM / migrations | SQLAlchemy 2.0 + Alembic | Standard, versioned schema |
| Data | pandas, numpy | Cleaning, features |
| Rainfall | imdlib, geopandas | IMD gridded data → district averages |
| Models | statsforecast (baselines), LightGBM (main, quantile) | Fast, strong on tabular lags, gives P10/P50/P90 |
| Explainability | SHAP (TreeExplainer) | "Why" panel |
| Scheduling | GitHub Actions cron | Free, logs visible |
| Bot | python-telegram-bot | Simple alerts |
| Frontend | React + Vite + TypeScript + Tailwind | Fast, typed |
| Charts | Recharts | Simple React charts |
| Data fetching | TanStack Query | Caching, loading states |
| Hosting | Render (API), Vercel (frontend) | Free tiers |
| Testing | pytest, Vitest | Backend + frontend |
| Lint/format | ruff, black, mypy; ESLint, Prettier | Consistent code |

## 3. Data model (core tables)

```
markets            (id, state, district, market_name, lat, lon, census_district)
commodities        (id, name, unit)                         -- unit = ₹/quintal
raw_prices         (id, source, market_id, commodity_id, variety, grade,
                    arrival_date, min_price, max_price, modal_price,
                    arrivals_tonnes NULL, ingested_at,
                    UNIQUE(source, market_id, commodity_id, variety, arrival_date))
rainfall_daily     (district, date, rain_mm, normal_mm)
ingestion_runs     (id, job, started_at, finished_at, status, rows_fetched,
                    rows_inserted, error)
quarantine_rows    (id, source, payload JSONB, reason, created_at)
features_weekly    (market_id, commodity_id, week_start, feature columns…)
model_runs         (id, trained_at, model_type, params JSONB, train_end_week,
                    backtest_metrics JSONB)
forecasts          (id, model_run_id, market_id, commodity_id, made_on_week,
                    target_week, horizon, p10, p50, p90, signal, drivers JSONB)
forecast_accuracy  (forecast_id, actual_price, abs_pct_error, evaluated_at)
subscriptions      (id, telegram_chat_id, commodity_id, market_id, created_at)
```

SQL views (in `sql/views/`):
- `v_prices_clean` — dedupe, drop/flag outliers (modal outside [min, max] or > 5× rolling median).
- `v_prices_weekly` — weekly modal price per market/commodity (median of daily modal).
- `v_volatility`, `v_seasonality` — analytics pages.

## 4. API endpoints (v1)

```
GET  /health
GET  /meta/commodities
GET  /meta/markets?commodity=onion
GET  /prices?commodity=onion&market=lasalgaon&freq=weekly&from=2024-01-01
GET  /forecast?commodity=onion&market=lasalgaon
GET  /forecast/best-mandi?commodity=onion&district=nashik
GET  /analytics/volatility?commodity=onion
GET  /analytics/seasonality?commodity=onion&market=lasalgaon
GET  /analytics/rainfall-impact?commodity=onion&market=lasalgaon
GET  /accuracy?commodity=onion&horizon=1
GET  /status/ingestion
GET  /export/weekly.csv?commodity=onion&market=lasalgaon
```

## 5. Folder structure

```
mandipulse/
├── docs/
│   ├── PRD.md
│   ├── Architecture.md
│   ├── Rules.md
│   ├── Phases.md
│   ├── Design.md
│   └── Memory.md            # created once coding starts
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app factory
│   │   ├── core/            # config.py, logging.py
│   │   ├── db/              # session.py, models.py
│   │   ├── schemas/         # Pydantic response models
│   │   ├── api/routes/      # prices.py, forecast.py, analytics.py, accuracy.py, status.py, meta.py
│   │   └── services/        # query logic used by routes
│   ├── ingestion/
│   │   ├── datagov_client.py
│   │   ├── ceda_backfill.py
│   │   ├── imd_rainfall.py
│   │   └── run_daily.py     # entry point
│   ├── pipeline/
│   │   ├── features.py
│   │   ├── baselines.py
│   │   ├── train.py
│   │   ├── predict.py
│   │   ├── evaluate.py
│   │   └── run_weekly.py    # entry point
│   ├── bot/
│   │   └── telegram_bot.py
│   ├── alembic/
│   ├── tests/
│   └── pyproject.toml
├── sql/
│   └── views/
├── notebooks/               # EDA only; never imported by app code
├── frontend/
│   ├── src/
│   │   ├── pages/           # Home, Explorer, Forecast, Analytics, Accuracy, Status
│   │   ├── components/      # charts/, ui/
│   │   ├── api/             # typed API client
│   │   ├── hooks/
│   │   └── lib/             # formatters (₹, dates)
│   └── package.json
├── .github/workflows/       # ci.yml, ingest.yml, weekly.yml
├── .env.example
└── README.md
```

## 6. Forecasting design

- **Target:** weekly modal price (₹/quintal) per market × commodity.
- **Validation:** walk-forward (expanding window), never random split. Backtest over the last 52 weeks.
- **Baselines:** naive (last week), seasonal naive (same week last year), ETS from statsforecast.
- **Main model:** one global LightGBM per commodity across markets, quantile objective at 0.1 / 0.5 / 0.9, one model per horizon (direct strategy).
- **Features:** price lags (1–8, 52 weeks), rolling mean/std, arrivals lags (if available), rainfall deviation lags (2–8 weeks), week-of-year, festival flags (Diwali, etc.), market ID as category.
- **Leakage guard:** every feature for target week *t + h* must use only data available at the end of week *t*.
- **Signal:** Rising if P50 > current × 1.10, Falling if < current × 0.90, else Stable.
- **Metrics:** MAPE, MASE (vs seasonal naive), P10–P90 coverage.

## 7. Environments & config

- All config via environment variables loaded in `core/config.py` (pydantic-settings).
- `.env.example` lists: `DATABASE_URL`, `DATAGOV_API_KEY`, `TELEGRAM_BOT_TOKEN`, `ALLOWED_ORIGINS`, `ENV`.
- Secrets live in GitHub Actions secrets / Render / Vercel env settings, never in the repo.
