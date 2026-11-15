"""Agent runs: list, steps (execution trace), live SSE stream, checkpoint history and replay."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from agent import db
from agent.settings import env
from apps.api.auth.security import current_user
from apps.api.queue import enqueue
from apps.api.streaming import run_stream

router = APIRouter(prefix="/api/runs", tags=["runs"])


def trace_link(trace_id: str) -> str | None:
    import os

    if os.environ.get("LANGSMITH_API_KEY"):
        return f"https://smith.langchain.com/search?q={trace_id}"
    return None


@router.get("")
async def list_runs(ref: str | None = None, user: dict = Depends(current_user)) -> list[dict]:
    if ref:
        return await db.fetch("SELECT * FROM runs WHERE user_id=%s AND ref_id=%s ORDER BY started_at DESC", user["id"], ref)
    return await db.fetch("SELECT * FROM runs WHERE user_id=%s ORDER BY started_at DESC LIMIT 100", user["id"])


@router.get("/{run_id}")
async def get_run(run_id: str, user: dict = Depends(current_user)) -> dict:
    r = await db.fetchone("SELECT * FROM runs WHERE run_id=%s AND user_id=%s", run_id, user["id"])
    if not r:
        raise HTTPException(404, "run not found")
    steps = await db.fetch("SELECT node, ts, data FROM run_steps WHERE run_id=%s ORDER BY id", run_id)
    return {"run": r, "steps": steps, "trace_link": trace_link(r["trace_id"])}


@router.get("/{run_id}/stream")
async def stream(run_id: str, user: dict = Depends(current_user)):
    if not await db.fetchone("SELECT 1 AS x FROM runs WHERE run_id=%s AND user_id=%s", run_id, user["id"]):
        raise HTTPException(404, "run not found")
    return run_stream(run_id)


@router.get("/threads/{job_id}/history")
async def history(job_id: str, user: dict = Depends(current_user)) -> list[dict]:
    """Checkpoint history of a job's bid thread (for replaying from any node)."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    from agent.graphs.bid_graph import build_bid_graph

    async with AsyncPostgresSaver.from_conn_string(env().database_url) as cp:
        g = build_bid_graph(cp)
        out = []
        async for snap in g.aget_state_history({"configurable": {"thread_id": f"bid:{user['id']}:{job_id}"}}):
            out.append({"checkpoint_id": snap.config["configurable"]["checkpoint_id"], "next": list(snap.next),
                        "created_at": snap.created_at, "status": snap.values.get("status")})
        return out


@router.post("/threads/{job_id}/replay/{checkpoint_id}")
async def replay(job_id: str, checkpoint_id: str, request: Request, user: dict = Depends(current_user)) -> dict:
    await enqueue("replay_from", user["id"], job_id, checkpoint_id, request.state.trace_id,
                  job_id=f"replay:{user['id']}:{job_id}:{checkpoint_id}")
    return {"queued": True}
