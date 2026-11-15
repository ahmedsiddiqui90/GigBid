# Runbook

## Run locally (Windows/macOS/Linux)

Prerequisites: Python 3.12, Node 22, Postgres 16, Redis 7 (or Docker).

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"    # .venv/bin on Linux/macOS
cp .env.example .env                                                # add GROQ_API_KEY (or set MODEL_PROFILE=offline)
python -m scripts.prepare_kaggle && python -m scripts.generate_synthetic && python -m rag.ingest.build
uvicorn gigsim.app:app --port 8081            # GigSim
python -m scripts.run_mcp_servers             # MCP: portfolio 8101, marketplace 8102, workspace 8103
python -m scripts.serve_api                   # API on 8000 (selector event loop, needed by psycopg on Windows)
python -m worker.main                         # Arq worker: schedules, graph runs, event polling
cd apps/web && npm install && npm run dev     # UI on 5173
```

Or everything with Docker: `docker compose -f infra/docker-compose.yml --env-file .env up --build` (UI on :8080).

Reviewer login is seeded on API start from `REVIEWER_EMAIL` / `REVIEWER_PASSWORD` with the AI/ML persona.

## Deployment (live link)

Hugging Face Docker Spaces and Render/Vercel free tiers cannot run this stack for free, so the graded link is served
from the author's machine through a **Cloudflare quick tunnel** (no account): `scripts/start_live.ps1` starts
Postgres, Redis, GigSim, the MCP servers, the API (which also serves the built UI) and the worker as background
processes, then runs `cloudflared tunnel --url http://localhost:8000` and writes the public URL to
`logs/public_url.txt`. If the machine restarts, run the script again (the URL changes; update the submission).
`infra/hf_space/` (single container) and `infra/docker-compose.yml` remain for any Docker host, e.g. an Oracle Cloud
Always Free VM.

## Schedules

| What | Interval | Why |
|---|---|---|
| Scout (GigSim) | per saved search, default 30 min (cron checks every minute which searches are due) | the simulator releases 5 new jobs every 10 minutes |
| Scout (live Upwork) | at least 240 min (`schedules.live_scout_minutes`) | a human freelancer checks a few times a day; polling faster would look like scraping and is not needed to win work |
| Event poll | every minute (GigSim), reads only our own proposals' events | keeps the pipeline board current |
| Degraded-mode retry | every 2 minutes, jobs in `waiting_marketplace` | recovers automatically after an outage |

Worker restarts are safe: Arq job ids dedupe enqueues, Scout dedupes by job id and content hash, analysis skips jobs
already awaiting approval or submitted, and marketplace writes use idempotency keys.

## Degraded mode (marketplace down)

Kill the marketplace MCP server or GigSim. `/api/health` reports `marketplace: false`; the UI shows a banner
("Marketplace unavailable..."); graph nodes catch `MarketplaceDown` (`agent/mcp_client.py`) and park the job as
`waiting_marketplace`; `retry_waiting` re-enqueues them when the server is back. Pending approvals are untouched.

## Crash during approval

Approvals live in the Postgres checkpointer (`interrupt()`) and the `approvals` table. Kill API/worker, restart, approve
in the UI: the worker resumes the thread and submits once (idempotency keys `draft-/submit-<user>:<job>:<draft hash>`).
Test: `pytest tests/integration/test_crash_resume.py`.

## Switching to live Upwork

Set `marketplace.adapter: upwork_live` in `agent/config.yaml` (or `MARKETPLACE_ADAPTER=upwork_live`), add
`UPWORK_CLIENT_ID/SECRET`, and connect the account in Settings (OAuth 2.1 + PKCE; token stored encrypted). Only the
adapter changes; graphs, tools and UI are identical. Proposals become drafts on Upwork that the user confirms there.

## Keys

Rotate `GROQ_API_KEY` in `.env`/Space secrets. `APP_SECRET_KEY` also derives the OAuth-token encryption key; rotating it
invalidates stored tokens (users reconnect).
