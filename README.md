# MandiPulse

Live mandi price intelligence and short-term (1–4 week) price forecasting for onion, tomato and potato in Indian mandis.

> Work in progress. See `docs/` for the PRD, architecture, phases and design.

## Local setup

**Backend** (Python 3.11):

```bash
cd backend
py -3.11 -m venv .venv            # or: python3.11 -m venv .venv
.venv/Scripts/activate            # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example .env           # then fill in DATABASE_URL
uvicorn app.main:app --reload
```

Check: `GET http://localhost:8000/health` → `{"status":"ok","db":"ok"}`

**Data** (needs `DATABASE_URL` and `DATAGOV_API_KEY` in `backend/.env`):

```bash
alembic upgrade head              # create/upgrade tables
python -m ingestion.backfill      # one-time history since 2019 (~2 min)
python -m ingestion.run_daily     # latest 10 days; idempotent
```

The daily job runs on GitHub Actions at 20:00 IST (`.github/workflows/ingest.yml`). It needs the
repo secrets `DATABASE_URL` and `DATAGOV_API_KEY`, and can also be started by hand from the
Actions tab ("Daily ingestion" → "Run workflow"). Run status: `GET /status/ingestion`.

**Frontend** (Node 22):

```bash
cd frontend
npm install
npm run dev
```
