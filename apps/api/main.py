"""GigBid API (FastAPI). Serves the built web app too, so one URL is enough for deployment."""
from __future__ import annotations

import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

if sys.platform == "win32":  # psycopg async needs the selector loop on Windows
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agent import db
from agent.safety.pii import install_pii_logging
from agent.settings import ROOT, config, env
from apps.api.auth.security import hash_password
from apps.api.routers import approvals, auth, jobs, messages, onboarding, runs, settings
from apps.api.schemas.models import Health


async def seed_reviewer() -> None:
    e = env()
    if not await db.fetchone("SELECT id FROM users WHERE email=%s", e.reviewer_email):
        await db.execute("INSERT INTO users (email, password_hash, name, persona_id, freelancer_id, settings) "
                         "VALUES (%s,%s,'Reviewer','ai_ml',%s,%s)", e.reviewer_email, hash_password(e.reviewer_password),
                         "fl-reviewer-ai_ml", db.j({"hourly_rate": 45, "floor_rate": 35, "weekly_connects": 80,
                                                     "autonomy": "auto_skip_low_fit"}))
        u = await db.fetchone("SELECT id FROM users WHERE email=%s", e.reviewer_email)
        await db.execute("INSERT INTO saved_searches (user_id, query, category, every_minutes) VALUES (%s,'',%s,30)",
                         u["id"], "ai_ml")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    install_pii_logging()
    await db.init_schema()
    await seed_reviewer()
    yield


app = FastAPI(title="GigBid API", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def trace_id(request: Request, call_next):
    """One trace id flows UI -> API -> worker -> graph -> MCP servers -> audit log."""
    request.state.trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex
    resp = await call_next(request)
    resp.headers["X-Trace-Id"] = request.state.trace_id
    return resp


for r in (auth.router, onboarding.router, jobs.router, approvals.router, messages.router, runs.router, settings.router):
    app.include_router(r)


@app.get("/api/health", response_model=Health, tags=["health"])
async def health() -> Health:
    mk = False
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.post(config().mcp["servers"]["marketplace"], headers={"Authorization": f"Bearer {env().mcp_bearer_token}",
                             "Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
                             json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                   "params": {"name": "get_market_stats", "arguments": {"category": "other"}}})
            mk = r.status_code == 200 and '"isError":true' not in r.text.replace(" ", "")
    except Exception:  # noqa: BLE001
        mk = False
    dbok, q = True, True
    try:
        await db.fetch("SELECT 1 AS x")
    except Exception:  # noqa: BLE001
        dbok = False
    try:
        from apps.api.queue import pool

        await (await pool()).ping()
    except Exception:  # noqa: BLE001
        q = False
    return Health(api=True, marketplace=mk, database=dbok, worker_queue=q, model_profile=config().profile,
                  marketplace_adapter=config().marketplace["adapter"])


DIST = ROOT / "apps" / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() and Path(path).parts[0] != ".." else DIST / "index.html")
