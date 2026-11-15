# 9. Safety and platform respect

**What GigBid must never do, and where it is enforced**

| Never | Enforcement |
|---|---|
| Submit a proposal, send a message or spend Connects without approval | `interrupt()` in `agent/nodes/approval.py` and `client_liaison.py` is the only path to `submit`/`send_reply`; write tools are allow-listed only to the `submitter`/`client_liaison` nodes; `autonomy` can only auto-skip |
| Submit twice / spend Connects twice | idempotency keys `draft-/submit-<user>:<job>:<draft hash>` checked in the Marketplace MCP server (Postgres `idempotency` table) **and** in GigSim; crash test `tests/integration/test_crash_resume.py` |
| Claim unsupported experience | claim splitting + verification + repair before the Critic (`rag/verify.py`), deterministic override for numbers/technologies, Compliance blocks if unsupported claims remain |
| Follow instructions planted in a job post or client message | untrusted text is delimited (`agent/safety/untrusted.py`), sentences matching injection patterns are stripped before the writer sees them, the analyst has no tools, risk/fit/decision/compliance are code, and Compliance removes tokens the injection asked for (canaries, quoted phrases, emails) |
| Put contact details, off-platform payment or guarantees in a draft | Compliance `strip` rules from `agent/policy.yaml` |
| Leak PII into logs/traces | `agent/safety/pii.py` log filter and masking of audit-log arguments |
| Leak OAuth tokens | Fernet-encrypted at rest (`apps/api/auth/security.py`), never logged, per-user rows; every query is scoped by `user_id` |
| Scrape or automate Upwork | live adapter uses only the official Upwork MCP server; no browser automation or cookies; live scouting at least every 240 min |

**What still gets through (known gaps)**

- Injections phrased without any trigger words ("the best proposals here mention the word X") are not stripped
  before the writer; only the canary/quote/email removal in Compliance catches the visible result.
- The deterministic verifier is word-overlap based: a paraphrase that changes meaning but keeps the words passes.
- Scam detection is pattern-based; a polite scam without payment/contact keywords and with a verified client passes.
- Hosted demo: the database lives inside the container, so restarting the Space resets state.
