"""Approvals: list pending interrupts and resume the interrupted graph thread (C5, D).

The pending approval is read from the approvals table (written when the graph interrupted), so a page
refresh or an API restart never loses it; resolving enqueues a resume of the checkpointed thread.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from agent import db
from apps.api.auth.security import current_user
from apps.api.queue import enqueue
from apps.api.schemas.models import ResolveIn

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("")
async def pending(user: dict = Depends(current_user)) -> list[dict]:
    return await db.fetch("SELECT id, thread_id, kind, ref_id, status, created_at, payload->>'job_title' AS title "
                          "FROM approvals WHERE user_id=%s AND status='pending' ORDER BY created_at DESC", user["id"])


@router.get("/{approval_id}")
async def get_approval(approval_id: int, user: dict = Depends(current_user)) -> dict:
    a = await db.fetchone("SELECT * FROM approvals WHERE id=%s AND user_id=%s", approval_id, user["id"])
    if not a:
        raise HTTPException(404, "approval not found")
    return a


@router.post("/{approval_id}/resolve")
async def resolve(approval_id: int, body: ResolveIn, request: Request, user: dict = Depends(current_user)) -> dict:
    a = await db.fetchone("SELECT * FROM approvals WHERE id=%s AND user_id=%s", approval_id, user["id"])
    if not a:
        raise HTTPException(404, "approval not found")
    if a["status"] != "pending":
        return {"queued": False, "reason": "already resolved"}
    if body.action == "reject" and not (body.reason or "").strip():
        raise HTTPException(422, "a reason is required to reject")
    await db.execute("UPDATE approvals SET status='resolving' WHERE id=%s AND status='pending'", approval_id)
    if a["kind"] == "proposal":
        await db.execute("UPDATE jobs SET status='resuming' WHERE user_id=%s AND job_id=%s", user["id"], a["ref_id"])
    # One resume per approval id, whatever the number of clicks or retries.
    await enqueue("resume_thread", user["id"], a["thread_id"], body.model_dump(), request.state.trace_id,
                  job_id=f"resume:{approval_id}")
    return {"queued": True, "trace_id": request.state.trace_id}
