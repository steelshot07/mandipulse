# Memory

Running log of decisions, gotchas and project state. Update at the end of every session (Rules.md).

## Current state (2026-11-26)
- **Phase 0 (setup) — done.** Backend/frontend scaffolds, CI, Supabase connected.
- **Phase 1 (schema + backfill) — done.** Migration `0001` applied to Supabase; backfill loaded
  44,404 daily price reports (2019-01-01 → 2026-11-25) for 17 market × commodity series.
  Re-run inserts 0. 4 rows quarantined per run (zero min or max price).
- **Next:** Phase 2 — `ingestion/run_daily.py` + `ingest.yml` cron, `GET /status/ingestion`.

## Decisions
- **Price source is data.gov.in, not CEDA.** CEDA only has monthly data. Resource
  `35985678-0d79-46b4-9ed6-6f13308a1d24` has daily history from 2002 (Architecture §6a).
  It has no arrivals quantity, so arrivals features are out for v1.
- **v1 markets** (`backend/app/core/markets.py`):
  - Onion (9): Lasalgaon, Lasalgaon (Niphad), Lasalgaon (Vinchur), Pimpalgaon Baswant,
    Pimpalgaon (Saykheda), Nashik, Manmad, Mandsaur, Bengaluru.
  - Tomato (5): Kolar, Chintamani, Madanapalle, Kalikiri, Azadpur.
  - Potato (3): Agra, Azadpur, Kolkata (Bara Bazar).
  - Dropped for short history: Indore (from Dec 2023) and Prayagraj (from Dec 2025).
  - The PRD target of ~10 markets per commodity isn't met for tomato/potato. Candidates if
    needed: Mulakalacheruvu (tomato), Bareilly and Farrukhabad (potato). Probe their name
    variants first.
- **Markets are matched by (state, normalised name) through an alias list**, not by
  district. The source renamed mandis from Nov 2025 (`Lasalgaon` → `Lasalgaon APMC` →
  `APMC Lasalgaon `) and moved some to new districts (Chittor → Annamayya, Kolar →
  Chikkaballapur, Bangalore → Bengaluru).
- **`raw_prices` keeps every distinct report.** Since 2024 the source has 2+ reports with
  different prices for the same market/variety/grade/day on 4–8% of days. The median modal
  gap is 1.3%. Prices are part of the unique key; `v_prices_weekly` must take the median.
  Identical reports (old/new name overlap) are stored once.
- **Backfill start: 2019-01-01.**
- **API access model:** public GETs are rate-limited per IP. Anything that writes, triggers
  a job or costs money needs `X-API-Key` (Rules.md §6).
- **RLS is enabled with no policies on every table**, so Supabase's public Data API can't
  reach them. The backend connects as owner.

## Gotchas
- data.gov.in returns **502 for Python's default User-Agent**. Always send our UA.
- data.gov.in URLs contain the API key. Never log them; httpx/httpcore loggers are pinned to
  WARNING.
- Prices are strings in old rows and numbers in new ones. Names have trailing spaces.
- The last page of a query overshoots `since` and can include very old rows (Agra 2012–17
  with zero min/max). The loader checks the date **before** validating, so these aren't
  quarantined.
- `Mandsaur(F&V)` and `Indore(F&V)` are separate yards, not aliases. The backfill warns
  about `Mandsaur(F&V)` on every run; this is expected.
- Supabase direct connections are IPv6-only, so use the **session pooler** URL.
- TypeScript is pinned to ~6.0 because typescript-eslint doesn't support TS 7 yet.
- DB tests (`-m db`) run only against `TEST_DATABASE_URL` (the CI Postgres service). Never
  point them at Supabase: the test downgrades the schema.

## Data notes
- Lasalgaon (Vinchur) starts in May 2020. Madanapalle is sparse before 2023 (38 rows in
  2022, dense from 2023).
- Bengaluru onion is thin in 2025 (255 rows) during the Bangalore → Bengaluru rename.
