# Engineering challenges

Real problems hit while building MandiPulse: how each was found, diagnosed and resolved.
Written to be retold (e.g. in interviews): situation → diagnosis → decision → result.

---

## 1. The data source only accepts connections from India (2026-11-27)

**Situation.** The daily ingestion job (`ingestion/run_daily.py`) worked locally: two runs
against the production database, with idempotent re-runs and correct failure logging. It was
scheduled on GitHub Actions (`.github/workflows/ingest.yml`, 20:00 IST). The first run on
GitHub failed.

**Symptoms, in order.**
1. First run: `ValueError: DATAGOV_API_KEY is not set`. The repo secrets had been saved in
   the wrong place, so GitHub passed empty strings. Re-adding them as *repository secrets*
   fixed it.
2. Second run: the database connected fine, but every call to `api.data.gov.in` failed with
   `ConnectError` / `ConnectTimeout`. The client retried 4 times with exponential backoff
   (2 s, 4 s, 8 s), then the run was marked `failed` and the job exited 1.

**Diagnosis.**
- The same code and API key worked from my machine, so the code and credentials weren't the
  problem.
- These were *connection-level* errors with no HTTP response at all, which pointed to the
  network rather than rate limiting (that would be a 429) or auth (a 401/403).
- Hypothesis: the server only accepts traffic from Indian IPs, and GitHub-hosted runners are
  in US/EU data centres.
- Test: I checked TCP reachability of `api.data.gov.in:443` from ~20 servers worldwide using a
  public multi-location network checker. **Only the Indian node connected (≈60 ms).** Nodes
  in Germany, Switzerland, Austria, Israel, Serbia and Slovenia got *connection refused*, and
  nodes in the US, Brazil, Poland and Bulgaria got *no route to host*. This confirmed a
  geo-restriction.

**Why it matters.** This is an infrastructure constraint, not a bug: no retry or config change
can fix it. The scheduled job has to run from a machine with an Indian IP.

**What went right.** The failure-handling design was proven in production. The run was
recorded as `failed` in `ingestion_runs`, no partial or corrupt data was written, the job
exited non-zero so GitHub flagged it, and the API key never appeared in the logs.

**Options considered.**
| Option | Pros | Cons |
|---|---|---|
| Serverless job in an Indian cloud region (AWS Lambda `ap-south-1` / GCP Cloud Run `asia-south1`) | Always on, free tier, no server to manage | Needs a cloud account and a deploy setup |
| Windows Task Scheduler on my PC | Zero cost, no new accounts | Only runs while the PC is on (the lookback window fills gaps) |
| Self-hosted GitHub runner on my PC | Keeps the Actions history | PC must be on; risky on a public repo (forked PRs could run code on it) |
| Free VM in India (e.g. Oracle Cloud, Mumbai) | Always on, free | I'd have to maintain a server |

**Decision.** Run the job as an **AWS Lambda in `ap-south-1` (Mumbai)**, triggered daily at
20:00 IST by **EventBridge Scheduler**.
- *Why Lambda over the alternatives:* it doesn't depend on my PC being on, there's no server to
  patch, and ~30 one-minute runs a month fit the always-free tier. It also needs no container
  image, unlike Cloud Run.
- *Infrastructure as code:* one CloudFormation template (`infra/aws/ingest-stack.yaml`) holds
  the function, schedule, IAM roles, 30-day log retention and an optional failure alarm (CloudWatch → email).
- *Deployment:* GitHub Actions still builds and ships the code, but only after CI passes on
  `main`. It signs in to AWS with **OIDC** (short-lived tokens, a role locked to this repo's
  main branch), so no AWS access keys are stored in GitHub. Building and deploying doesn't
  call data.gov.in, so the geo-block doesn't affect it.
- *What didn't change:* the ingestion code. The same `run_cli` path runs behind a thin Lambda
  handler, which raises on failure so Lambda and the alarm see it.

**Result.** _Pending: stack deploy + first run from Mumbai._ <!-- Fill in: did Mumbai reach data.gov.in, first run stats, 3-day check. -->

**Takeaways.**
- Check *where* a job runs, not just *whether* the code works. Government and regional APIs
  are often geo-restricted.
- Tell failures apart by layer: no response at all (network) vs 4xx (auth or limits) vs 5xx
  (server).
- Test hypotheses cheaply. A multi-location reachability check gave a clear answer in
  seconds, before I changed any infrastructure.
- Designing for failure from day one (run logging, idempotent writes, non-zero exits) made
  this a non-event for data integrity.
