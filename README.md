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
python -m ingestion.imd_rainfall backfill   # one-time: 1991-2020 normals + rainfall since 2019 (~1 GB, ~25 min)
python -m ingestion.imd_rainfall recent     # last 21 days (weekly on GitHub Actions)
python ../notebooks/eda.py        # print the numbers behind docs/Findings.md
```

The daily job runs as an AWS Lambda in Mumbai at 20:00 IST, because data.gov.in only accepts
Indian IPs (see `docs/Challenges.md`). One-time setup: `.\infraws\deploy_stack.ps1`, then set
repo variable `AWS_DEPLOY_ROLE_ARN`. After that, code changes deploy automatically after CI
(`.github/workflows/deploy-ingest.yml`). Run status: `GET /status/ingestion`.

**Frontend** (Node 22):

```bash
cd frontend
npm install
npm run dev
```
