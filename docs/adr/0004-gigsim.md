# ADR 0004: our own GigSim

**Decision:** the starter kit shipped no simulator, so gigsim/ implements one (REST, rate limits, 5xx, Connects, idempotency, deterministic simulated clients) and is frozen by checksum.
**Why:** repeatable evaluation of reply/hire rate without touching a real marketplace.
