# ADR 0002: numpy vector index instead of a vector database

**Decision:** per-persona embeddings (fastembed BGE-small, CPU) stored as a numpy matrix; exact cosine search; BM25 via bm25s.
**Why:** a persona has under 100 items; exact search takes milliseconds; no extra service to run or deploy.
**Revisit if:** portfolios grow past ~50k chunks.
