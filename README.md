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

**Frontend** (Node 22):

```bash
cd frontend
npm install
npm run dev
```
