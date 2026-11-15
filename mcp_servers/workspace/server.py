"""Workspace MCP server: calendar slots, tentative interview holds, email drafts.

Backed by a local mock (Postgres tables + deterministic busy blocks) instead of Google Calendar/Gmail;
the agent only ever sees these MCP tools, so a Google backend could replace `_busy()` and the inserts.

Run: python -m mcp_servers.workspace.server   (streamable HTTP on :8103/mcp)
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from agent import db
from mcp_servers.common.guard import audit, caller

mcp = FastMCP("gigbid-workspace", instructions="Freelancer calendar and email drafts (mock backend).",
              stateless_http=True, json_response=True)
WORK_HOURS = (9, 17)


def _busy(user: str, day: datetime) -> set[int]:
    """Deterministic pseudo-busy hours per user/day (stands in for a real calendar)."""
    h = int(hashlib.md5(f"{user}{day.date()}".encode()).hexdigest()[:6], 16)
    return {WORK_HOURS[0] + (h % 8), WORK_HOURS[0] + ((h >> 4) % 8)}


class Slot(BaseModel):
    start: str
    end: str


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False))
async def free_slots(days_ahead: int = 5, duration_minutes: int = 30, max_slots: int = 4, ctx: Context = None) -> dict:
    """Free interview slots on weekdays within working hours (UTC), excluding existing holds."""
    user, trace = caller(ctx)
    holds = await db.fetch("SELECT start_ts FROM workspace_holds WHERE user_id=%s AND start_ts > now()", user)
    taken = {h["start_ts"].replace(minute=0, second=0, microsecond=0) for h in holds}
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    slots: list[dict] = []
    for d in range(1, days_ahead + 1):
        day = now + timedelta(days=d)
        if day.weekday() >= 5:
            continue
        for hr in range(WORK_HOURS[0], WORK_HOURS[1]):
            start = day.replace(hour=hr)
            if hr in _busy(user, day) or start in taken:
                continue
            slots.append(Slot(start=start.isoformat(), end=(start + timedelta(minutes=duration_minutes)).isoformat()).model_dump())
            break  # one slot per day keeps offers spread out
        if len(slots) >= max_slots:
            break
    await audit("workspace", "free_slots", user, trace, {"days_ahead": days_ahead}, {"n": len(slots)})
    return {"slots": slots}


class HoldInput(BaseModel):
    start: str = Field(description="ISO-8601 start time of one of the offered slots")
    duration_minutes: int = Field(default=30, ge=15, le=120)
    title: str = Field(min_length=3, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=200)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
async def create_tentative_hold(input: HoldInput, ctx: Context = None) -> dict:
    """Place a tentative calendar hold for an interview slot (idempotent)."""
    user, trace = caller(ctx)
    start = datetime.fromisoformat(input.start)
    await db.execute("INSERT INTO workspace_holds (user_id, start_ts, end_ts, title, idem) VALUES (%s,%s,%s,%s,%s) "
                     "ON CONFLICT (idem) DO NOTHING", user, start, start + timedelta(minutes=input.duration_minutes),
                     input.title, input.idempotency_key)
    await audit("workspace", "create_tentative_hold", user, trace, input.model_dump(), {"ok": True})
    return {"ok": True, "start": input.start, "title": input.title}


class DraftInput(BaseModel):
    to: str = Field(min_length=1, max_length=200, description="Recipient (client name or thread id)")
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False))
async def create_email_draft(input: DraftInput, ctx: Context = None) -> dict:
    """Save an email draft for the freelancer to review (never sends)."""
    user, trace = caller(ctx)
    await db.execute("INSERT INTO workspace_drafts (user_id, recipient, subject, body) VALUES (%s,%s,%s,%s)",
                     user, input.to, input.subject, input.body)
    await audit("workspace", "create_email_draft", user, trace, {"to": input.to, "subject": input.subject}, {"ok": True})
    return {"ok": True, "status": "draft"}


def http_app():
    from mcp_servers.common.guard import BearerAuth

    app = mcp.streamable_http_app()
    app.add_middleware(BearerAuth)
    return app


def main() -> None:
    import uvicorn

    uvicorn.run(http_app(), host="0.0.0.0", port=8103)


if __name__ == "__main__":
    main()
