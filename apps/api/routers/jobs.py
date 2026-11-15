"""Job inbox, job detail, pipeline board, paragraph regeneration."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from agent import db
from agent.llm import llm_text
from apps.api.auth.security import current_user
from apps.api.queue import enqueue
from apps.api.schemas.models import JobRow, RegenerateIn

router = APIRouter(prefix="/api", tags=["jobs"])
STAGES = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"]


def _row(r: dict) -> JobRow:
    j = r["job"] or {}
    a = r.get("analysis") or {}
    return JobRow(job_id=r["job_id"], title=j.get("title", r["job_id"]), category=j.get("category"), status=r["status"],
                  decision=r.get("decision"), fit=r.get("fit"), risk=r.get("risk"),
                  risk_flags=(a.get("risk") or {}).get("flags", []), price=r.get("price"),
                  connects=j.get("connects_cost"), budget=j.get("budget") or {}, stage=r.get("stage"),
                  updated_at=str(r.get("updated_at")))


@router.get("/jobs", response_model=list[JobRow])
async def inbox(status: str | None = None, decision: str | None = None, user: dict = Depends(current_user)) -> list[JobRow]:
    rows = await db.fetch("SELECT * FROM jobs WHERE user_id=%s ORDER BY (decision='bid') DESC NULLS LAST, fit DESC NULLS LAST, "
                          "updated_at DESC LIMIT 300", user["id"])
    out = [_row(r) for r in rows]
    if status:
        out = [r for r in out if r.status == status]
    if decision:
        out = [r for r in out if r.decision == decision]
    return out


@router.get("/jobs/{job_id}")
async def job_detail(job_id: str, user: dict = Depends(current_user)) -> dict:
    r = await db.fetchone("SELECT * FROM jobs WHERE user_id=%s AND job_id=%s", user["id"], job_id)
    if not r:
        raise HTTPException(404, "job not in your inbox")
    appr = await db.fetchone("SELECT id, status, payload, resolution, created_at FROM approvals WHERE thread_id=%s "
                             "ORDER BY id DESC LIMIT 1", f"bid:{user['id']}:{job_id}")
    runs = await db.fetch("SELECT run_id, status, trace_id, started_at, finished_at FROM runs WHERE user_id=%s AND ref_id=%s "
                          "ORDER BY started_at DESC", user["id"], job_id)
    return {"row": _row(r).model_dump(), "job": r["job"], "analysis": r["analysis"], "approval": appr, "runs": runs}


@router.post("/jobs/{job_id}/analyse")
async def analyse(job_id: str, request: Request, user: dict = Depends(current_user)) -> dict:
    r = await db.fetchone("SELECT status FROM jobs WHERE user_id=%s AND job_id=%s", user["id"], job_id)
    if not r:
        raise HTTPException(404, "job not in your inbox")
    if r["status"] in ("awaiting_approval", "submitted"):
        return {"queued": False, "reason": f"job is {r['status']}"}
    await db.execute("UPDATE jobs SET status='queued' WHERE user_id=%s AND job_id=%s", user["id"], job_id)
    await enqueue("analyse_job", user["id"], job_id, request.state.trace_id, job_id=f"analyse:{user['id']}:{job_id}:{request.state.trace_id[:8]}")
    return {"queued": True, "trace_id": request.state.trace_id}


@router.post("/jobs/{job_id}/skip")
async def skip(job_id: str, user: dict = Depends(current_user)) -> dict:
    await db.execute("UPDATE jobs SET status='skipped', decision='skip', updated_at=now() WHERE user_id=%s AND job_id=%s",
                     user["id"], job_id)
    return {"ok": True}


@router.get("/pipeline")
async def pipeline(user: dict = Depends(current_user)) -> dict:
    rows = await db.fetch("SELECT * FROM jobs WHERE user_id=%s AND stage IS NOT NULL ORDER BY updated_at DESC", user["id"])
    cols = {s: [] for s in STAGES}
    for r in rows:
        cols.setdefault(r["stage"], []).append(_row(r).model_dump())
    return {"stages": STAGES, "columns": cols}


@router.post("/jobs/{job_id}/regenerate")
async def regenerate(job_id: str, body: RegenerateIn, user: dict = Depends(current_user)) -> dict:
    """Rewrite one paragraph (the user then approves via 'edit', so Compliance re-checks it)."""
    appr = await db.fetchone("SELECT payload FROM approvals WHERE thread_id=%s AND status='pending'", f"bid:{user['id']}:{job_id}")
    if not appr:
        raise HTTPException(404, "no pending draft")
    ev = appr["payload"].get("evidence", {})
    ev_block = "\n".join(f"[{k}] {v.get('snippet', '')[:300]}" for k, v in ev.items())
    text, _ = await llm_text("proposal_writer", "regenerate_paragraph", lambda: body.paragraph,
                             paragraph=body.paragraph, instruction=body.instruction, evidence=ev_block)
    return {"paragraph": text}
