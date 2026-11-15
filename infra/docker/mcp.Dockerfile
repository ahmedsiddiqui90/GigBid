# GigBid mcp service (same base layers as the other Python services, so builds share the cache)
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY pyproject.toml ./
COPY agent agent
COPY rag rag
COPY mcp_servers mcp_servers
COPY gigsim gigsim
COPY worker worker
COPY apps/api apps/api
COPY apps/__init__.py apps/__init__.py
COPY evals evals
COPY scripts scripts
COPY data/personas data/personas
COPY data/gigsim data/gigsim
COPY data/policy_pack data/policy_pack
RUN pip install -e . && python -m rag.ingest.build
EXPOSE 8101 8102 8103
CMD ["python", "-m", "scripts.run_mcp_servers"]
