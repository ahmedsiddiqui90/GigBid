"""Arq worker: scheduled scouting, graph runs, approvals resume, event polling (E1).

Idempotency: Arq job ids dedupe enqueues; Scout dedupes by job id + content hash in the jobs table;
graph writes use marketplace idempotency keys, so a worker restart never double-analyses or double-submits.
Run: python -m arq worker.main.WorkerSettings   (or python -m worker.main)
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from arq import cron
from arq.connections import RedisSettings

from agent import db
from agent.mcp_client import MarketplaceDown, call
from agent.memory.store import record_outcome
from agent.nodes.scout import scout
from agent.runner import graphs, resume, run_bid, run_conversation
from agent.safety.pii import install_pii_logging
from agent.settings import ROOT, config, env

log = logging.getLogger("worker")


async def startup(ctx):
    install_pii_logging()
    await db.init_schema()
    ctx["graphs_cm"] = graphs()
    ctx["g"] = await ctx["graphs_cm"].__aenter__()


async def shutdown(ctx):
    await ctx["graphs_cm"].__aexit__(None, None, None)


async def _user(uid: int) -> dict:
    return await db.fetchone("SELECT * FROM users WHERE id=%s", uid)


async def scout_user(ctx, user_id: int, trace_id: str = "scheduled") -> int:
    u = await _user(user_id)
    if not u or not u.get("persona_id"):
        return 0
    seen = await db.fetch("SELECT job_id, dedupe_hash FROM jobs WHERE user_id=%s", user_id)
    ids, hashes = {r["job_id"] for r in seen}, {r["dedupe_hash"] for r in seen}
    n = 0
    for s in await db.fetch("SELECT * FROM saved_searches WHERE user_id=%s", user_id):
        try:
            new = await scout(user_id, trace_id, s["query"], s["category"], ids, hashes, limit=15)
        except MarketplaceDown as e:
            log.warning("scout: marketplace down (%s)", e)
            return n
        for j in new:
            h = j.pop("dedupe_hash")
            await db.execute("INSERT INTO jobs (user_id, job_id, dedupe_hash, job, status) VALUES (%s,%s,%s,%s,'queued') "
                             "ON CONFLICT DO NOTHING", user_id, j["job_id"], h, db.j(j))
            await ctx["redis"].enqueue_job("analyse_job", user_id, j["job_id"], trace_id,
                                           _job_id=f"analyse:{user_id}:{j['job_id']}")
            n += 1
        await db.execute("UPDATE saved_searches SET last_run=now() WHERE id=%s", s["id"])
    return n


async def analyse_job(ctx, user_id: int, job_id: str, trace_id: str = "scheduled") -> str:
    u = await _user(user_id)
    row = await db.fetchone("SELECT job, status FROM jobs WHERE user_id=%s AND job_id=%s", user_id, job_id)
    if row and row["status"] in ("awaiting_approval", "submitted", "resuming"):
        return f"skip: already {row['status']}"  # idempotent: never re-analyse a job waiting for or past approval
    await db.execute("UPDATE jobs SET status='analysing', updated_at=now() WHERE user_id=%s AND job_id=%s", user_id, job_id)
    res = await run_bid(ctx["g"], u, job_id, row["job"] if row and row["job"] else None, trace_id)
    return res["status"]


async def resume_thread(ctx, user_id: int, thread_id: str, answer: dict, trace_id: str = "-") -> str:
    res = await resume(ctx["g"], await _user(user_id), thread_id, answer, trace_id)
    return res["status"]


async def run_conversation_job(ctx, user_id: int, thread: str, trace_id: str = "-") -> str:
    res = await run_conversation(ctx["g"], await _user(user_id), thread, trace_id)
    return res["status"]


async def replay_from(ctx, user_id: int, job_id: str, checkpoint_id: str, trace_id: str = "-") -> str:
    """Re-run a job's bid thread from any checkpoint (time travel)."""
    g = ctx["g"]["bid"]
    cfg = {"configurable": {"thread_id": f"bid:{user_id}:{job_id}", "checkpoint_id": checkpoint_id}}
    out = await g.ainvoke(None, cfg)
    return str(out.get("status"))


async def reindex_user(ctx, user_id: int) -> str:
    from rag.ingest.build import build_persona

    u = await _user(user_id)
    d = ROOT / "data" / "uploads" / str(user_id)
    idx = build_persona(u["persona_id"], [d] if d.exists() else [])
    return f"{len(idx.items)} items"


STAGE_OF = {"viewed": "viewed", "replied": "replied", "interview": "interview", "hired": "hired", "lost": "lost"}
ORDER = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"]


async def poll_events(ctx) -> int:
    """Marketplace events -> pipeline board, outcome memory, and conversation runs for new client replies."""
    n = 0
    users = await db.fetch("SELECT * FROM users WHERE persona_id IS NOT NULL")
    if not users:
        return 0
    from agent.memory.store import open_store

    async with open_store() as store:
        for u in users:
            since = int((u.get("settings") or {}).get("events_since", 0))
            try:
                ev = (await call("scout", u["id"], "poll", "list_events",
                                 {"freelancer_id": u["freelancer_id"], "since": since})).get("events", [])
            except MarketplaceDown:
                return n
            for e in ev:
                job = await db.fetchone("SELECT job, stage FROM jobs WHERE user_id=%s AND job_id=%s", u["id"], e["job_id"])
                if job:
                    new = STAGE_OF.get(e["type"])
                    if new and (job["stage"] is None or ORDER.index(new) > ORDER.index(job["stage"] or "drafted")):
                        await db.execute("UPDATE jobs SET stage=%s, updated_at=now() WHERE user_id=%s AND job_id=%s",
                                         new, u["id"], e["job_id"])
                    cat = (job["job"] or {}).get("category", "other")
                    # outcome memory only from confirmed marketplace events (viewed = a submitted proposal)
                    await record_outcome(store, str(u["id"]), cat, "submitted" if e["type"] == "viewed" else e["type"])
                if e["type"] == "replied" and e.get("thread_id"):
                    await ctx["redis"].enqueue_job("run_conversation_job", u["id"], e["thread_id"], "event",
                                                   _job_id=f"conv:{u['id']}:{e['thread_id']}:first")
                since = max(since, e["id"])
                n += 1
            s = {**(u.get("settings") or {}), "events_since": since}
            await db.execute("UPDATE users SET settings=%s WHERE id=%s", db.j(s), u["id"])
    return n


async def scheduled_scout(ctx) -> int:
    """Every minute: run saved searches that are due (live mode uses a slower, conservative interval)."""
    live = config().marketplace["adapter"] == "upwork_live"
    floor = config().schedules["live_scout_minutes"] if live else 0
    n = 0
    now = datetime.now(timezone.utc)
    for s in await db.fetch("SELECT * FROM saved_searches"):
        every = max(s["every_minutes"], floor)
        if s["last_run"] is None or (now - s["last_run"]).total_seconds() >= every * 60:
            await ctx["redis"].enqueue_job("scout_user", s["user_id"], _job_id=f"scout:{s['user_id']}:{int(now.timestamp() // 60)}")
            n += 1
    return n


async def retry_waiting(ctx) -> int:
    """Degraded mode recovery: jobs parked while the marketplace was down are retried once it is back."""
    rows = await db.fetch("SELECT user_id, job_id FROM jobs WHERE status='waiting_marketplace' LIMIT 20")
    for r in rows:
        await ctx["redis"].enqueue_job("analyse_job", r["user_id"], r["job_id"], "retry",
                                       _job_id=f"analyse:{r['user_id']}:{r['job_id']}:retry:{int(datetime.now().timestamp() // 120)}")
    return len(rows)


class WorkerSettings:
    functions = [scout_user, analyse_job, resume_thread, run_conversation_job, replay_from, reindex_user]
    cron_jobs = [cron(scheduled_scout, second=0), cron(poll_events, second=30), cron(retry_waiting, minute=set(range(0, 60, 2)), second=15)]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(env().redis_url)
    max_jobs = 2
    job_timeout = 600
    keep_result = 3600


if __name__ == "__main__":
    from arq import run_worker

    run_worker(WorkerSettings)
