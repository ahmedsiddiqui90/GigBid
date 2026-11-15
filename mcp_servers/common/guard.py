"""Shared MCP server plumbing: bearer auth, caller identity, per-user rate limit, audit log, idempotency.

Callers (GigBid agents) send:
  Authorization: Bearer <MCP_BEARER_TOKEN>
  X-GigBid-User: <user id>       (rate limiting, tenancy, audit)
  X-Trace-Id: <trace id>         (one trace id from UI -> API -> graph -> MCP -> audit log)
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from agent.safety.pii import mask_obj
from agent.settings import ROOT, env

log = logging.getLogger("mcp.guard")


class BearerAuth(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.headers.get("authorization") != f"Bearer {env().mcp_bearer_token}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def caller(ctx: Context | None) -> tuple[str, str]:
    """(user_id, trace_id) from HTTP headers; defaults for in-memory/stdio use."""
    try:
        req = ctx.request_context.request  # type: ignore[union-attr]
        if req is not None:
            return req.headers.get("x-gigbid-user", "anonymous"), req.headers.get("x-trace-id", "-")
    except (AttributeError, LookupError, ValueError):
        pass
    return "local", "-"


class RateLimiter:
    """Sliding-window limiter per user, kept below the marketplace's own limit."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)

    def check(self, user: str) -> None:
        now = time.time()
        q = self.hits[user]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_minute:
            raise RuntimeError(f"rate limit: max {self.per_minute} marketplace calls/minute per user")
        q.append(now)


_AUDIT_FALLBACK = ROOT / "data" / "processed" / "audit_fallback.jsonl"


async def audit(server: str, tool: str, user: str, trace: str, args: dict, result: Any) -> None:
    """Append-only audit row (PII masked). Falls back to a local JSONL file if Postgres is down."""
    row = {"server": server, "tool": tool, "user_id": user, "trace_id": trace,
           "args": mask_obj(args), "result": mask_obj(_summ(result))}
    try:
        from agent import db

        await db.execute("INSERT INTO audit_log (user_id, server, tool, args, result, trace_id) VALUES (%s,%s,%s,%s,%s,%s)",
                         user, server, tool, db.j(row["args"]), db.j(row["result"]), trace)
    except Exception as e:  # noqa: BLE001
        log.warning("audit db write failed (%s); using file", type(e).__name__)
        Path(_AUDIT_FALLBACK).parent.mkdir(parents=True, exist_ok=True)
        with open(_AUDIT_FALLBACK, "a", encoding="utf-8") as f:
            f.write(json.dumps({**row, "ts": time.time()}, default=str) + "\n")


def _summ(result: Any) -> Any:
    s = json.dumps(result, default=str)
    return result if len(s) < 2000 else {"truncated": s[:2000]}


async def idem_get(key: str) -> dict | None:
    from agent import db

    row = await db.fetchone("SELECT result FROM idempotency WHERE key=%s", key)
    return row["result"] if row else None


async def idem_put(key: str, server: str, result: dict) -> None:
    from agent import db

    await db.execute("INSERT INTO idempotency (key, server, result) VALUES (%s,%s,%s) ON CONFLICT (key) DO NOTHING",
                     key, server, db.j(result))
