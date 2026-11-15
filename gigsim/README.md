# GigSim (our simulator)

The starter kit shipped no marketplace simulator, so GigBid includes this small one. Treat it as
frozen: CI checks `gigsim/CHECKSUM` and fails if the code changes.

- Seed data: `data/gigsim/jobs.json` (synthetic dev jobs + duplicates + 300 real Kaggle jobs),
  `clients.json` (synthetic client histories with **hidden** preferences), `market_stats.json` (real).
- Auth: `Authorization: Bearer $GIGSIM_API_TOKEN`. Rate limit `GIGSIM_RATE_LIMIT`/min → 429 + `Retry-After`.
  Random 503s at `GIGSIM_ERROR_RATE`.
- Writes need an `Idempotency-Key` header; replays return the stored result and never spend Connects twice.
- Connects cost comes from `agent/policy.yaml` (`connects`), so a platform policy update is a config change.
- **Simulated client** (`client_decision`): deterministic score from must-have skill coverage, evidence
  citations, length, generic opening (if the client dislikes them), price vs hidden ceiling, and penalties
  for off-platform contact or injected canary words, plus seeded noise. Reply / interview / hire are
  thresholds on that score. Scam clients always answer with an off-platform request.
- New jobs drip in: 5 more every 10 minutes (or `POST /admin/tick`).
- `GIGSIM_INCLUDE_HIDDEN=1` loads the held-out test split for the final test run.

Run: `uvicorn gigsim.app:app --port 8081`
