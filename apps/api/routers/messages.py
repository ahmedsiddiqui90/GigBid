from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from agent import db
from agent.mcp_client import MarketplaceDown, call
from apps.api.auth.security import current_user
from apps.api.queue import enqueue

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.get("")
async def threads(request: Request, user: dict = Depends(current_user)) -> dict:
    try:
        res = await call("client_liaison", user["id"], request.state.trace_id, "list_messages",
                         {"freelancer_id": user["freelancer_id"]})
    except MarketplaceDown as e:
        return {"threads": [], "marketplace_unavailable": True, "error": str(e)}
    pend = {a["thread_id"]: a for a in await db.fetch(
        "SELECT id, thread_id, payload FROM approvals WHERE user_id=%s AND kind='message' AND status='pending'", user["id"])}
    out = []
    for t in res.get("threads", []):
        a = pend.get(f"conv:{user['id']}:{t['thread_id']}")
        out.append({**t, "pending_approval": {"id": a["id"], **a["payload"]} if a else None})
    return {"threads": out, "marketplace_unavailable": False}


@router.post("/{thread_id}/draft")
async def draft_reply(thread_id: str, request: Request, user: dict = Depends(current_user)) -> dict:
    await enqueue("run_conversation_job", user["id"], thread_id, request.state.trace_id,
                  job_id=f"conv:{user['id']}:{thread_id}:{request.state.trace_id[:8]}")
    return {"queued": True}
