# Phases — MandiPulse

Build one phase at a time. Each phase ends with acceptance checks that must pass before moving on. Rough time estimates assume part-time work.

---

## Phase 0 — Project setup (1–2 days)
**Build**
- Repo with folder structure from `Architecture.md` §5.
- `backend/pyproject.toml` with core deps; `frontend/` via Vite + React + TS + Tailwind.
- `core/config.py` (pydantic-settings), `core/logging.py`, `.env.example`.
- Postgres on Supabase/Neon; Alembic initialised.
- `ci.yml`: ruff, black --check, mypy, pytest; ESLint + Vitest for frontend.
- FastAPI app with `GET /health`.

**Done when**
- `GET /health` returns `{"status":"ok","db":"ok"}` locally.
- CI is green on an empty test suite.

---

## Phase 1 — Schema + historical backfill (3–5 days)
**Build**
- Alembic migration for `markets`, `commodities`, `raw_prices`, `ingestion_runs`, `quarantine_rows`.
- `ingestion/ceda_backfill.py`: load downloaded CEDA files for onion/tomato/potato into `raw_prices`.
- Confirm and lock the v1 market list in config after inspecting real market names.
- Create `docs/Memory.md`.

**Done when**
- At least 3 years of daily history loaded for the chosen markets.
- Re-running the backfill inserts 0 new rows (idempotent).
- Quarantine table has reasons for every rejected row.

---

## Phase 2 — Live daily ingestion (2–3 days)
**Build**
- `ingestion/datagov_client.py` with timeout, retries, pagination.
- `ingestion/run_daily.py` entry point; logs to `ingestion_runs`.
- `ingest.yml` GitHub Actions cron (daily 20:00 IST).
- `GET /status/ingestion`.

**Done when**
- Job has run successfully on GitHub Actions for 3 consecutive days.
- Manually re-running the job on the same day adds no duplicates.
- A simulated API failure marks the run failed without corrupting data.

---

## Phase 3 — Cleaning + analytics (4–6 days) ← analytics milestone
**Build**
- SQL views: `v_prices_clean`, `v_prices_weekly`, `v_volatility`, `v_seasonality`.
- `ingestion/imd_rainfall.py`: district daily rainfall + normals → `rainfall_daily`.
- EDA notebook: volatility, seasonality, rainfall-lag correlation. Write 3–5 key findings.
- API: `/prices`, `/analytics/*`, `/meta/*`.

**Done when**
- Weekly series exists for every v1 market × commodity with documented gap handling.
- Outlier rule is tested.
- Key findings written in `docs/Findings.md` with numbers from the notebook.

---

## Phase 4 — Baselines + model + backtest (5–7 days)
**Build**
- `pipeline/features.py` with leakage-guard test.
- `pipeline/baselines.py`: naive, seasonal naive, ETS.
- `pipeline/train.py`: LightGBM quantile (0.1/0.5/0.9), one per horizon, per commodity.
- Walk-forward backtest over last 52 weeks; store results in `model_runs`.

**Done when**
- Backtest table shows MAPE, MASE and P10–P90 coverage for every model × commodity × horizon.
- Model vs seasonal naive is reported honestly (even if the model loses somewhere).
- Leakage test passes.

---

## Phase 5 — Forecast pipeline + API (3–4 days)
**Build**
- `pipeline/predict.py` writes to `forecasts` with signal + SHAP top drivers.
- `pipeline/evaluate.py` fills `forecast_accuracy` for matured forecasts.
- `run_weekly.py` + `weekly.yml` cron.
- API: `/forecast`, `/accuracy`, `/forecast/best-mandi`.

**Done when**
- Weekly job runs end-to-end on GitHub Actions.
- Old forecasts are never overwritten (check row counts across two runs).
- `/forecast` returns P10/P50/P90, signal and drivers for every v1 series.

---

## Phase 6 — Frontend dashboard (6–8 days)
**Build** (following `Design.md`)
- Pages: Home (overview cards), Explorer (price charts, compare), Forecast, Analytics, Status.
- Loading / empty / error / stale states on every view.
- Mobile-first layout.

**Done when**
- All pages work on a 375 px wide screen.
- Lighthouse performance ≥ 85 on mobile.
- No `any` types; Vitest covers formatters and API client.

---

## Phase 7 — Accuracy page + monitoring (2–3 days)
**Build**
- Accuracy page: forecast vs actual chart, MAPE/MASE vs baseline by horizon.
- Stale-data banner when a series is > 7 days old.
- Failed-job notification (GitHub Actions email or Telegram message to you).

**Done when**
- Accuracy page shows at least 4 weeks of live evaluated forecasts.
- Turning off ingestion for a test series triggers the stale banner.

---

## Phase 8 — Telegram alerts (2–3 days)
**Build**
- Bot commands: `/start`, `/subscribe <commodity> <market>`, `/unsubscribe`, `/price`.
- Weekly digest + alert if forecast move exceeds threshold.

**Done when**
- You and 2 friends receive a correct weekly digest.
- Unsubscribe stops messages immediately.

---

## Phase 9 — Deploy + polish (2–3 days)
**Build**
- API on Render, frontend on Vercel, env vars set.
- README: problem, live link, architecture diagram, screenshots, backtest table, honest limitations.
- Optional: Metabase / Power BI analytics view; CSV export.

**Done when**
- Live URL works from a phone on mobile data.
- README lets a stranger run it locally in < 15 minutes.
- Resume bullets written using real numbers from the accuracy page.
