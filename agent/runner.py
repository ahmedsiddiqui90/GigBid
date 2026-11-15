"""Runs graphs durably: Postgres checkpointer + store, progress events to Redis (for SSE), execution
trace to runs/run_steps, interrupts to the approvals table, job status to the jobs table.

thread ids: bid:{user}:{job}   conv:{user}:{thread}
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from langgraph.types import Command

from agent import db
from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from agent.settings import ROOT, env

log = logging.getLogger("runner")


@asynccontextmanager
async def graphs():
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.store.postgres.aio import AsyncPostgresStore

    async with AsyncPostgresSaver.from_conn_string(env().database_url) as cp, \
            AsyncPostgresStore.from_conn_string(env().database_url) as store:
        await cp.setup()
        await store.setup()
        yield {"bid": build_bid_graph(cp, store), "conversation": build_conversation_graph(cp, store), "store": store,
               "checkpointer": cp}


async def _publish(run_id: str, event: dict) -> None:
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(env().redis_url)
        await r.publish(f"run:{run_id}", json.dumps(event, default=str))
        await r.aclose()
    except Exception:  # noqa: BLE001 - streaming is best-effort; the DB trace is authoritative
        pass


def _langsmith_cfg(run_id: str, trace_id: str, thread_id: str) -> dict:
    return {"run_name": thread_id, "metadata": {"trace_id": trace_id, "run_id": run_id, "thread_id": thread_id},
            "tags": [thread_id.split(":")[0]]}


async def _drive(graph, inp: Any, thread_id: str, run_id: str, trace_id: str, user_id: int, kind: str, ref_id: str) -> dict:
    cfg = {"configurable": {"thread_id": thread_id}, **_langsmith_cfg(run_id, trace_id, thread_id)}
    await db.execute("INSERT INTO runs (run_id, user_id, thread_id, graph, ref_id, status, trace_id) VALUES (%s,%s,%s,%s,%s,'running',%s) "
                     "ON CONFLICT (run_id) DO NOTHING", run_id, user_id, thread_id, kind, ref_id, trace_id)
    await _publish(run_id, {"type": "run", "status": "running"})
    try:
        async for mode, chunk in graph.astream(inp, cfg, stream_mode=["custom", "updates"]):
            if mode == "custom":
                await _publish(run_id, {"type": "node", **chunk})
            elif mode == "updates":
                for node_name, upd in chunk.items():
                    if node_name == "__interrupt__":
                        continue
                    data = upd if isinstance(upd, dict) else {}
                    await db.execute("INSERT INTO run_steps (run_id, node, data) VALUES (%s,%s,%s)", run_id, node_name,
                                     db.j({k: v for k, v in data.items() if k not in ("usage",)}))
    except Exception as e:  # noqa: BLE001 - dead-letter: the job cannot complete
        log.exception("run failed")
        await db.execute("UPDATE runs SET status='dead_letter', error=%s, finished_at=now() WHERE run_id=%s", str(e)[:1000], run_id)
        await _publish(run_id, {"type": "run", "status": "dead_letter", "error": str(e)[:300]})
        return {"status": "dead_letter", "error": str(e)}
    snap = await graph.aget_state(cfg)
    state = snap.values
    pending = [i for t in snap.tasks for i in t.interrupts]
    status = "awaiting_approval" if pending else state.get("status", "done")
    await db.execute("UPDATE runs SET status=%s, finished_at=now(), usage=%s WHERE run_id=%s", status,
                     db.j(state.get("usage", [])), run_id)
    if pending:
        payload = pending[0].value
        exists = await db.fetchone("SELECT id FROM approvals WHERE thread_id=%s AND status='pending'", thread_id)
        if not exists:
            await db.execute("INSERT INTO approvals (user_id, thread_id, kind, ref_id, payload) VALUES (%s,%s,%s,%s,%s)",
                             user_id, thread_id, payload.get("kind", kind), ref_id, db.j(payload))
    await _publish(run_id, {"type": "run", "status": status})
    return {"status": status, "state": state}


async def _sync_job(user_id: int, job_id: str, thread_id: str, res: dict) -> None:
    st = res.get("state", {})
    status = res["status"]
    stage = {"submitted": "submitted", "awaiting_approval": "drafted"}.get(status)
    await db.execute(
        "UPDATE jobs SET status=%s, thread_id=%s, decision=%s, fit=%s, risk=%s, price=%s, analysis=%s, "
        "stage=COALESCE(%s, stage), proposal_id=COALESCE(%s, proposal_id), updated_at=now() WHERE user_id=%s AND job_id=%s",
        status, thread_id, (st.get("decision") or {}).get("action"), (st.get("fit") or {}).get("score"),
        (st.get("risk") or {}).get("score"), (st.get("price") or {}).get("amount"),
        db.j({k: st.get(k) for k in ("job_spec", "risk", "fit", "decision", "price", "critique", "compliance",
                                      "verification", "errors", "strategy", "submission", "approval")}),
        stage, (st.get("submission") or {}).get("proposal_id"), user_id, job_id)


async def run_bid(g: dict, user: dict, job_id: str, job: dict | None = None, trace_id: str | None = None) -> dict:
    thread_id = f"bid:{user['id']}:{job_id}"
    run_id = uuid.uuid4().hex[:12]
    trace_id = trace_id or uuid.uuid4().hex
    profile = json.loads((ROOT / "data" / "personas" / user["persona_id"] / "profile.json").read_text())
    inp = {"user_id": user["id"], "persona": user["persona_id"], "freelancer_id": user["freelancer_id"],
           "floor_rate": user.get("settings", {}).get("floor_rate", profile["floor_rate"]),
           "hourly_rate": user.get("settings", {}).get("hourly_rate", profile["hourly_rate"]),
           "job_id": job_id, "run_id": run_id, "trace_id": trace_id, **({"job": job} if job else {})}
    res = await _drive(g["bid"], inp, thread_id, run_id, trace_id, user["id"], "bid", job_id)
    await _sync_job(user["id"], job_id, thread_id, res)
    return {"run_id": run_id, "thread_id": thread_id, **res}


async def resume(g: dict, user: dict, thread_id: str, answer: dict, trace_id: str | None = None) -> dict:
    kind = "bid" if thread_id.startswith("bid:") else "conversation"
    run_id = uuid.uuid4().hex[:12]
    ref = thread_id.split(":", 2)[2]
    await db.execute("UPDATE approvals SET status='resolved', resolution=%s, resolved_at=now() WHERE thread_id=%s AND status='pending'",
                     db.j(answer), thread_id)
    res = await _drive(g[kind], Command(resume=answer), thread_id, run_id, trace_id or uuid.uuid4().hex, user["id"], kind, ref)
    if kind == "bid":
        await _sync_job(user["id"], ref, thread_id, res)
    return {"run_id": run_id, "thread_id": thread_id, **res}


async def run_conversation(g: dict, user: dict, thread: str, trace_id: str | None = None) -> dict:
    thread_id = f"conv:{user['id']}:{thread}"
    run_id = uuid.uuid4().hex[:12]
    trace_id = trace_id or uuid.uuid4().hex
    inp = {"user_id": user["id"], "persona": user["persona_id"], "freelancer_id": user["freelancer_id"],
           "thread_id": thread, "run_id": run_id, "trace_id": trace_id, "status": None}
    return {"run_id": run_id, "thread_id": thread_id,
            **await _drive(g["conversation"], inp, thread_id, run_id, trace_id, user["id"], "conversation", thread)}


def new_trace_id() -> str:
    return f"{int(time.time())}-{uuid.uuid4().hex[:12]}"
