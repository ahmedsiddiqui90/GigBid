# ADR 0006: single-container deployment on a Hugging Face Space

**Decision:** infra/hf_space runs Postgres, Redis, GigSim, MCP, API and worker in one free Docker Space.
**Why:** free, 16 GB RAM (models fit), public URL. Render/Vercel free tiers cannot run the worker and models.
**Trade-off:** data is container-local; a restart re-seeds. docker-compose remains the reference multi-service setup.
