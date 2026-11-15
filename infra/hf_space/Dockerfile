# Single-container deployment for a free Hugging Face Docker Space (16 GB RAM, 2 vCPU).
# Runs Postgres, Redis, GigSim, the three MCP servers, the API (which also serves the built web UI)
# and the Arq worker in one container. Data lives inside the container: a Space restart re-seeds it.
FROM node:22-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
RUN npx vite build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends postgresql redis-server && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HOME=/home/user
COPY pyproject.toml ./
COPY agent agent
COPY rag rag
COPY mcp_servers mcp_servers
COPY gigsim gigsim
COPY worker worker
COPY apps/__init__.py apps/__init__.py
COPY apps/api apps/api
COPY evals evals
COPY scripts scripts
COPY data/personas data/personas
COPY data/gigsim data/gigsim
COPY data/policy_pack data/policy_pack
COPY infra/hf_space/start.sh /app/start.sh
COPY --from=web /web/dist apps/web/dist
RUN pip install -e . && python -m rag.ingest.build && chown -R user:user /app && chmod +x /app/start.sh
USER user
ENV APP_ENV=production DATABASE_URL=postgresql://user@localhost:5432/gigbid REDIS_URL=redis://localhost:6379/0 \
    GIGSIM_BASE_URL=http://localhost:8081 MODEL_PROFILE=open REVIEWER_EMAIL=reviewer@gigbid.dev
EXPOSE 7860
CMD ["/app/start.sh"]
