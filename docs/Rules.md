# Rules — for the AI coding assistant

Read `PRD.md`, `Architecture.md`, `Phases.md` and `Memory.md` (if it exists) before writing any code. If anything here conflicts with a request, ask before proceeding.

## 1. Working style

- Work on **one phase at a time** from `Phases.md`. Don't start the next phase until the current one's acceptance criteria pass.
- Before coding, state in 3–5 lines what you'll change and which files you'll touch.
- Make small, reviewable changes. Don't rewrite files that aren't part of the current task.
- If something is unclear (an API field, a market name, a design choice), **ask — don't guess**.
- Never invent API fields, dataset columns or library functions. If unsure, write a small probe script to inspect the real response first.
- At the end of every session, update `Memory.md` (template below).

## 2. Stack rules

**Use:** the libraries listed in `Architecture.md` §2.

**Don't use without asking first:**
- Any new dependency (Python or npm). Say why it's needed.
- Deep learning frameworks (TensorFlow, PyTorch) — LightGBM is the main model in v1.
- Prophet (heavy install; statsforecast covers baselines).
- Redux or other global state libraries (TanStack Query + local state is enough).
- CSS-in-JS libraries or component kits other than Tailwind (no MUI, no Bootstrap).
- Celery / Redis (GitHub Actions cron handles scheduling).

**Versions:** Python 3.11, SQLAlchemy 2.0 style (`select()`, not legacy `Query`), Pydantic v2.

## 3. Code standards

### Python
- Type hints on all functions; must pass `mypy` on `app/`, `ingestion/`, `pipeline/`.
- Format with black, lint with ruff.
- Docstrings for public functions: one line on what it does, plus args/returns if non-obvious.
- No business logic in route handlers. Routes call `services/`.
- No `print()` — use the logger from `core/logging.py`.
- Notebooks are for exploration only; anything reused moves into `pipeline/` with tests.

### TypeScript / React
- Strict TypeScript, no `any`.
- Functional components + hooks only.
- All API calls go through `src/api/`, typed from backend schemas.
- Formatting of ₹, numbers and dates only via helpers in `src/lib/`.

### SQL
- Schema changes only through Alembic migrations. Never edit the DB by hand.
- Views live in `sql/views/` as `.sql` files and are applied by a migration.

## 4. Data & ML rules (non-negotiable)

- **Never use a random train/test split** for time series. Walk-forward validation only.
- **No future leakage:** features for target week t+h use only data available at the end of week t. Add a test for this.
- Always compare against the seasonal-naive baseline and report it next to the model.
- Never overwrite past forecasts. Each retrain writes new rows linked to a `model_run_id`.
- Raw tables are append/upsert only. Cleaning happens in views or the feature step, never by mutating raw data.
- Don't silently drop data. Bad rows go to `quarantine_rows` with a reason.
- Prices are ₹/quintal everywhere. Convert at ingestion if a source differs and record that.

## 5. Error handling

- **External APIs (data.gov.in, IMD):** timeout 30 s, retry 3× with exponential backoff, then log failure to `ingestion_runs` and exit non-zero so GitHub Actions marks it failed.
- One bad record must never crash a whole run: validate per row with Pydantic, quarantine failures, continue.
- Ingestion is idempotent: re-running the same day must not create duplicates (use upserts on the unique key).
- **API:** return proper status codes (400 bad params, 404 unknown market/commodity, 503 if data is stale beyond 7 days for that series). Error body: `{"error": {"code": "...", "message": "..."}}`.
- Never expose stack traces or secrets in API responses.
- **Frontend:** every data view handles loading, empty, error and stale-data states. Always show "Last updated".

## 6. Security

- No secrets in code, commits, logs or notebooks. Use `.env` (git-ignored) and update `.env.example` when adding a variable.
- CORS restricted to `ALLOWED_ORIGINS`.
- Validate all query params with Pydantic / FastAPI types.
- Telegram bot stores only `chat_id` and subscriptions — no names or phone numbers.

## 7. Testing

- Every new pipeline function gets a pytest test with a small fixture dataset.
- Required tests: ingestion upsert idempotency, outlier flagging, weekly aggregation, leakage guard, metric calculations, each API route (happy path + one error).
- CI (`ci.yml`) runs lint, type check and tests on every push. Don't merge red.

## 8. What the AI must NOT do

- Don't mark a phase done without running its acceptance checks.
- Don't claim accuracy numbers that weren't produced by the evaluation code.
- Don't add features outside the current phase "while you're at it".
- Don't delete migrations, data, or tests to make something pass.
- Don't hard-code market lists or thresholds in multiple places; they belong in config.
- Don't generate fake or synthetic data for anything shown to users. Synthetic data is allowed only in tests, clearly named.

## 9. Memory.md template

Create `docs/Memory.md` when Phase 1 coding starts, and update it at the end of every session:

```markdown
# Memory — MandiPulse

## Current status
- Phase: <n — name>, <in progress / done>
- Last updated: <YYYY-MM-DD>

## Done
- <short bullet per completed item, with file paths>

## In progress / next step
- <the exact next thing to do>

## Decisions made (and why)
- <e.g. "Weekly price = median of daily modal, because some markets report once a week">

## Known issues / gotchas
- <e.g. "data.gov.in returns market name 'Lasalgaon(Niphad)' for some rows">

## Key facts about the data
- <field names, date formats, quirks discovered>
```

Keep it under ~150 lines. Summarise older entries instead of letting it grow forever.
