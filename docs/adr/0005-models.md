# ADR 0005: open-weight models via Groq, offline heuristic profile

**Decision:** profile 'open' routes cheap nodes to gpt-oss-20b and writer/critic/liaison to gpt-oss-120b on Groq; profile 'offline' runs deterministic heuristics with the same interfaces.
**Why:** the deployed link must run without paid APIs or a GPU; CI and large evals need a free deterministic mode.
**Trade-off:** free-tier rate limits; fallback model (llama-3.1-8b-instant) then heuristics.
